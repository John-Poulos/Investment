# M10 — Macro & narrative

Status: MVP design decided 2026-10-25 (sitting 4, D-M10-1…8, every recommended option; Q10.2a after the owner's FRED check, Q10.3a + GNPDEF + STD); Part 1 next (wave W8) · Updated: 2026-10-25 · Outline headings: Understand why an asset is or is not moving (items 1, 3, 4); Killswitch (item 3, events for M11); Analyze the financials (item 5, CPI and M2 for M01's hurdle) · Depends on: M00 (`signal`, prices, news, events, corpus passages), M04 (4a gate rows, 4b-lite text rows, model tags), M09 (SPY, `technicals/bars.py`, `technicals/earnings.py`), M02 7b (`official/fedreg.py`) · Sources: S68, S86, S94, S-new-M10-n (pack; numbered into SOURCES.md at Part 1)

Research: `docs/M10_DESIGN_PACK.md`; MVP cut and sitting record: `docs/mvp/M10_MVP_BRIEF.md`; cross-module plan: `docs/mvp/MVP_PLAN.md`. Thresholds marked † are starting values, never tuned on the watchlist alone (D32). Missing data stays missing, never zero (D-M04-9). Research signals and warnings, not financial advice; exit and killswitch signals stay warnings (D16).

## Purpose
Per market and per equity: what is the macro and policy backdrop, which names are exposed to the parts of it in stress, and what is on file when a name moves ("if you don't know why it moves you have no edge"). M10 explains and warns; it does not forecast a regime (the pack's forecasting and backtest rounds are deferred). M11 owns the killswitch; M10 supplies its events. Served elsewhere and only read here: money flow and crowding (M02), future earnings (guidance ledger, R19), short squeezes (M07), "edge but not moving" (M01 rule 5, M11). "Wars" and "the narrative" have no MVP signal (GPR and narrative tracking deferred).

## Inputs
| Data | Source (stored in; code) | Grade | Refresh |
|---|---|---|---|
| Macro series: T10Y3M, DGS10, BAA10Y, NFCI, SAHMREALTIME (state); CPIAUCSL, M2SL (M01 hurdle, YoY shown); GNPDEF (M04 Ohlson O); DFF, UNRATE (display, D32) | FRED keyless `fredgraph.csv` (S-new-M10-17), `macro/fred.py` → `macro_series` with our own vintage dates (Part 1, 0045, DS23) | A ("stale since <date>" when a release is missed) | Daily step; weekly and monthly series only when due; ≤ 10 requests a run |
| Financing dependence | M04 4a rows `survival_gate`, `runway_q`, `maturity_wall`, `fcf_burn` (`financials/gate_step.py`) | A | Per filing |
| Credit distress text | M04 4b-lite rows `covenant_status`, `gc_language` (`financials/gate_text_step.py`) | A | Per filing |
| Model tags | `config/company_models.toml` (`asset_treasury`, `fund`, `spac_shell`), SIC from `entity` | Owner / A | On edit |
| Prices | `price_bar`: the name and SPY (`prices/store.py` `BENCHMARK`); completed weeks `technicals/bars.py` | A (D-M04-82) | Daily prices step |
| Catalysts | `event`, earnings via `technicals/earnings.py`, `news_item` (from early 2026-10), `guidance` changes, `policy_event`, regime and gate state changes | A / B / C | Per run |
| Policy documents | Federal Register: BIS and presidential documents (`official/fedreg.py` extension, Part 2, 0047) | A | Daily, 2–4 requests |
| Company exposure text | corpus `passage` (10-K/10-Q, earnings 8-Ks, call turns), verbatim quotes (D21) | A filing / B call | Per filing |
| Config | `config/macro.toml` (zones, persistence; Part 1), `config/macro_topics.toml` (topics, agencies, lexicon; owner-approved; Part 2) | Owner | On edit |

## Signals out
Market readings go to `macro_reading` (no CIK, D-M10-1). Company rows: `module_id = "M10"`, keyed by `cik`, one row per timeframe; states in `value_text`; missing = "missing: <reason>". All rows info (weight 0) until a backtest (D-M10-8).

| Signal | value / value_text | Meaning | MY | PT | ST | Grade |
|---|---|---|---|---|---|---|
| `macro_regime` (`macro_reading`) | latest weekly value; normal / watch / stress / stale; composite = count in stress | State per indicator with its own as-of and last-change date; no single score | info | info | info | A |
| `macro_exposure_warning` | warn / watch / none / not_applicable / not_mapped; class and indicators in `method` | The company's own M04 rows make it sensitive to an indicator in stress | info (warning) | info | info | weakest of A and the M04 row |
| `policy_event_exposure` (Part 2) | 1; confirmed / stated / mentioned | A new BIS rule or presidential document on a topic the company's own text names | info (warning; M11 input) | info | info (alert) | A document + filing quote; B call quote or owner confirmation |
| `move_context` | weekly excess-return z vs SPY; catalyst_on_file / no_catalyst_on_file / before_coverage / insufficient_history | What the engine knows inside a big move; the owner may write the "because" | info | info | info (alert on no_catalyst) | A for the move; with catalysts the weakest catalyst's; owner sentence B |

Shown with the signals (D32, no D13 rows): every fetched series with value, as-of, state and last change; CPI and M2 year-over-year; DFF and UNRATE; every company's class (none, not applicable and not mapped included), warning and last weekly move.

## Timeframe parameters
| Parameter | MY | PT | ST |
|---|---|---|---|
| Persistence | stress from the 4th weekly reading in zone (monthly Sahm: 2nd)† | same | same |
| Warning use | shown, kept for M11 (weight 0) | info | info; `no_catalyst` and policy items alert |
| Move window | 1 completed week vs the name's own 52 weeks | same | same |

## Rules
1. **Readings.** Daily series become Friday weekly averages; each reading keeps its release date and our fetch date (vintage); revisions add rows, old rows kept; history before the first download is labelled "revisions may leak". Blank or "." = missing.
2. **Zones†.** T10Y3M < 0 (capped at watch); DGS10 up ≥ 1.00 pp in 26 weeks; BAA10Y ≥ its trailing 10-year 90th percentile of weekly readings; NFCI > 0; SAHMREALTIME ≥ 0.50. **Watch** = in zone for fewer than 4 weekly readings; **stress** from the 4th (Sahm: 1 = watch, 2 = stress).
3. **Classes** (from the company's own rows; a name may hold both of the first two; asset-holding replaces them):
   - credit-sensitive: `survival_gate` warn / fail, numeric `runway_q` < 8 (D-M04-32), `maturity_wall` ≥ 1 (D-M04-33), or `covenant_status` / `gc_language` at warn / fail;
   - long-duration: TTM FCF < 0 (`fcf_burn`);
   - asset-holding: `asset_treasury` (watch at most);
   - not applicable: `fund`; not mapped: SIC 6000–6799 (banks, insurers); no class: `spac_shell` periods; missing: M04 rows missing (e.g. SPCX's incomplete gate).
4. **Warnings.** Credit-sensitive: BAA10Y and NFCI both in stress → warn, one of them → watch. Long-duration: the DGS10 rate shock in stress → warn. T10Y3M and SAHMREALTIME warn no company (Macro page and composite only).
5. **Policy events (Part 2).** Agency watch on BIS and `PRESDOCU`; topics and lexicon from `config/macro_topics.toml` (tariffs/trade, export controls; an agency list per topic), matched on title and abstract; event date = the earliest stated date (signed, effective, published); links from the company's own text: stated = an amount or impact sentence, mentioned = risk factors or MD&A only (a banner, never a trip); the owner confirms links on the Macro page (the D8 review place, no queue kind). One action in 8-K, news and the Register is one event with several sources.
6. **Move context.** Weekly excess return vs SPY on completed weeks; |z| ≥ 2† vs the name's own 52 weeks lists the stored catalysts in the window (earnings via the shared rule, news, 8-K events, guidance changes, policy events, regime and gate changes); none → `no_catalyst_on_file`; window before the news store → `before_coverage`; < 52 weeks of prices → `insufficient_history`. A catalyst on file is not a cause: only the owner writes "because".
7. **First runs are baselines** (FRED history, Federal Register from 2025-01-01, past moves): shown, never alerted.

## Failure modes
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Revised series (NFCI) | Backfilled history is the revised series; the owner's probe already showed the 2026-10-02 NFCI move from −0.494 (checked 2026-10-12) to −0.508 | Own vintages from day one; pre-download history labelled "revisions may leak"; ALFRED at tuning |
| Missed release, deleted series, failed fetch | A stale value read as current | "stale since <date>", never carried forward; the run continues |
| Flicker around a zone (T10Y3M 2025) | Many short episodes | Persistence (rule 2) |
| Curve inversion 2022–24, Sahm Jul 2024 | Long false alarms | T10Y3M capped at watch; neither warns a company alone |
| Short credit spike (April 2025: BAA10Y 1.73 → 2.02; NFCI peaked −0.381 on 2025-04-11, never > 0) | One-week spikes warn, or a level percentile never trips | Both BAA10Y and NFCI needed; 4-week persistence; the build replays April 2025 on the fetched series (the 10-year p90 is unverified) |
| M04 class proxies | Capex-heavy growers (AMZN, BA) and utilities read long-duration; bitcoin swings (MSTR) look like duration | Labelled proxies; MSTR watch at most; Q10.5b (cash burners only) is the tuning alternative |
| Banks and insurers (D32) | FCF and the gate are not meaningful; rate exposure runs the other way | "class not mapped (financials)", never none |
| Policy watch is semiconductor-built (D32) | FAA, FDA, CMS, EPA, FERC, bank-regulator rules unseen; "no exposure" for non-tech names | "no policy topic configured"; agencies per topic in the toml; non-tech fixture |
| Export-control boilerplate in every risk-factor section | Every chip name "exposed" | Mentioned = banner only; stated or confirmed links only trip |
| Keyword matches (drones, firearms in BIS lists) | False events | Agency + type filters; lexicon on title/abstract; owner confirmation |
| Reversals (press release, court) | An issued rule read as in force | "as issued; later changes not checked" |
| SPY benchmark (D32) | Poor fit for small caps, ADRs, sector moves; market-wide days | Labelled "vs SPY"; sector ETFs at tuning |
| Catalyst grades | 97% of Finnhub items are C (D-M02-59) | One event takes its best source's grade; a move whose only catalyst is C reads C |
| Coincidence | A catalyst on file read as the cause | Only the owner's sentence says "because" (B) |
| `fredgraph.csv` | A graph download, not the documented API; Claude's sandbox was reset on it (2026-10-25) while the owner's PC worked | Owner-run fetches; free key + API as the fallback (Q10.2b) |
| Licences | SPY (Tiingo) and BAA10Y (Moody's-derived) redistributed | Internal display only (D-UI-2, S68); BAA10Y terms checked at build |

## Decisions
- D-M10-1 (2026-10-25, sitting 4, Q10.1a): market readings in new tables `macro_series` (series, date, value, vintage_date, source, licence) and `macro_reading`; per-company effects in `signal`. Why: `signal` is keyed by a real CIK (D-M04-74), and 0000000000 is already migration 0029's unresolved fallback.
- D-M10-2 (2026-10-25, Q10.2a): FRED keyless `fredgraph.csv`, storing our own vintages from day one; a free key and the ALFRED backfill wait for tuning. Why: the owner's one-request check (`logs/fred_probe.txt`, NFCI 2026-09-04…10-16) returned rows from the PC; no owner action; the backtest that needs vintages is deferred (S-new-M10-17, -18). The key route (b) is the fallback if the CSV stops working.
- D-M10-3 (2026-10-25, Q10.3a + GNPDEF + STD): series T10Y3M, DGS10, BAA10Y, NFCI, SAHMREALTIME (with state), CPIAUCSL and M2SL (M01 hurdle, YoY shown), GNPDEF (fills M04's hand-entered Ohlson O deflator, D-M04-87; M04's reader is switched at Part 1 under the next free D-M04), DFF and UNRATE (display only, D32): at most 10 requests a run. BAA10Y is the market credit spread M10 uses; HY OAS (D-M02-42's named series, ICE licence) is not fetched in the MVP (Round 1). Why: curve, rates, credit, conditions and labour with BAA10Y back to 1986 (S-new-M10-1, -4, -17, -21); standard macro rows for every reader (D32).
- D-M10-4 (2026-10-25, Q10.4a): stress after 4 weekly readings in zone (Sahm 2 monthly); a credit warning needs BAA10Y and NFCI both in stress (one = watch). Why: filters the 2025 curve flicker and the April 2025 spike (pack 6.2a, S86).
- D-M10-5 (2026-10-25, Q10.5a + the defaults): classes from M04's rows (rule 3): long-duration on any negative TTM FCF (RIVN, ORCL, INFQ, AMZN, BA on the 2026-10-13 logs); `covenant_status` / `gc_language` warn or fail join the credit class (GFS on the 2026-10-13 log); SIC 6000–6799 reads not mapped. Why: rows already built on stored data (D-M04-31…33, D-M04-95…99; D31); investment-driven negative FCF is also distant cash flow (S-new-M10-9). D9: AMZN and BA by a hair.
- D-M10-6 (2026-10-25, Q10.6a): policy events from an agency watch (BIS, `PRESDOCU`) on the 7b adapter, 2–4 requests a day; topics from owner-approved `config/macro_topics.toml`; links from the company's own text (stated / mentioned); owner confirms on the Macro page; event date = earliest stated date. Why: one adapter and budget; publication lags 6–12 days (pack 5.1a, 5.3a; S94, S-new-M10-30). D32: the topics are semiconductor-built (failure modes).
- D-M10-7 (2026-10-25, Q10.7a): `move_context` on the stored SPY bars and the shared week and earnings readers, |z| ≥ 2† vs the name's own 52 completed weeks, 0 requests. Why: outline M10 items 3–4; every input is stored (S68).
- D-M10-8 (2026-10-25, Q10.8a): every M10 row is info (weight 0) before a backtest; warnings are shown and kept for M11. Why: many predictors fail out of sample (S-new-M10-5, -6); about 8 recessions to test on (S-new-M10-25).

## Deferred to tuning
Round 1: EBP/GSW, Engstrom–Sharpe, regional surveys, IPMAN/IPG3344S, HY OAS (ICE licence, 3-year window), net liquidity (no peer-reviewed support). Round 2: free key, ALFRED backfill, backtest, hit / false-alarm / miss records. Round 3: betas, sector ETFs, geographic revenue and floating-rate debt (M04 additions), `rating_action` (DS17) as a credit input. Round 4: `narrative_topic_rise`, `m10_phrase`, EPU/TPU/GPR. Round 5: Congress, reversal tracking, USTR/ITA/FCC/DoD and FAA filters. Round 6: killswitch templates and shared exposure (M11, R23).

## Build parts
**Part 1 — Macro series, regime, exposure, moves** (wave W8; branch `m10-part1`; migration `0045_m10_macro`; D-STO-35 (FRED in the refresh); D-UI-44; DS23 row; decisions from D-M10-9). Code: `src/engine/macro/` `fred.py` (keyless CSV, U7 budget, vintages; shared with M12), `regime.py`, `exposure.py`, `moves.py` (reuses `technicals/bars.py`, `technicals/earnings.py`), `step.py` (local step after M09; FRED once a day, weekly and monthly series only when due); `scripts/run_macro.py`; `config/macro.toml`; M04 `distress.py` reads GNPDEF from `macro_series` (next free D-M04). Tables `macro_series`, `macro_reading`, `move_note`. UI: Macro page (states, as-of dates, last change, composite, standard rows, licence label); one M10 line per company on Overview (class, warning, last move with catalysts, sentence box). Live check: `uv run python scripts/run_macro.py regime` (≤ 10 FRED requests, 0 SEC, under 2 min; `--no-fetch` for re-runs). Fixtures: hand-built CSVs from real values (T10Y3M 2022-10…2025-09, BAA10Y and HY OAS Apr 2025, the owner's NFCI 2025-01…2026-10 download); synthetic bars with SPY; M04 rows for RIVN, AMZN, MSTR, ETV, SPCX, GFS; D32 cases: a regulated utility, a regional bank.

**Part 2 — Policy events and stated exposure** (wave W9; branch `m10-part2`; migration `0047_m10_policy`; D-STO-37; D-UI-46; next free D-M02 for the `fedreg.py` extension). Code: agency / type query in `official/fedreg.py`; `macro/topics.py` (lexicon, verbatim quotes, stated vs mentioned); `macro/policy.py`. Tables `policy_event` (three dates, agency, type, status, topics, grade, source_ref), `policy_link` (cik, level, quote, passage_id, owner_confirmed_at). Config `config/macro_topics.toml`. UI: event list with link confirm / reject on the Macro page; policy rows on Overview; policy events become move catalysts. Live check: `uv run python scripts/run_macro.py policy` (Federal Register from 2025-01-01, about 6–10 requests, 0 SEC, under 3 min). Fixtures: FR 2026-01052 (Proclamation 11002) and 2025-00636; a quantified passage and boilerplate; a non-tech document with no topic configured.

## Live checks (owner runs, sends the log)
- Part 1: `uv run python scripts/run_macro.py regime`.
- Part 2: `uv run python scripts/run_macro.py policy`.

## Open questions
- Does the BAA10Y 10-year 90th percentile ever trip in a short shock (April 2025 replay at Part 1)? If not, a change-based zone is a tuning candidate (needs a source first, D6).
- M11 reads the warnings and policy events (sitting 5); until then they show on the pages only (M01 rule 4).
