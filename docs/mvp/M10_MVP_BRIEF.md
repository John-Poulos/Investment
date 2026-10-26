# M10 Macro & narrative — MVP brief
Updated 2026-10-25 (refreshed for sitting 4) · Source: docs/M10_DESIGN_PACK.md (research) · Status: for owner decision (sitting 4)

Research signals and warnings only, not advice. Nothing here is decided until the owner answers (D7). Answers become D-M10-1 onward in a new `docs/M10_MACRO.md`; an amendment to another module takes that module's next free number (D-M01-10, D-M04-108).

## Since 2026-10-13 (what the refresh changed)
- **SPY is stored** (M09 Part 1, PR #47: `prices/store.py` `BENCHMARK = "SPY"`, fetched in `prices_step`). Q10.7 now costs 0 extra requests.
- **Shared readers are built** and M10 reuses them, never a second copy (MVP_PLAN item 3): completed weeks `technicals/bars.py` (`weekly`, `monday_of`, the `spac_shell` cut-off); earnings in the window `technicals/earnings.py` (`earnings_in_window`, `accepted_clock`, foreign 6-K reports); the M01 rule readers `m01_rules.py` (rule 4 list, which M11 reads).
- **M04 4b-lite is built** (PR #45): `gc_language` and `covenant_status` rows (warn / fail classes, D-M04-95…99). The 2026-10-13 log has GFS and SPCX at covenant warn ("breach or default waived or cured"), no fail. The brief had them in Round 3; they now join the credit-sensitive class as a default (Starting rules; strike it if you disagree).
- **News coverage** has run since early October 2026 (M02 Part 7a), so `before_coverage` applies only to moves before then.
- **Pre-assigned numbers** (MVP_PLAN): Part 1 `0045_m10_macro`, D-STO-35, D-UI-44 (Macro page, Overview line), DS23 (FRED macro series); Part 2 `0047_m10_policy`, D-STO-37, D-UI-46 (policy event list), next free D-M02 for the `fedreg.py` extension. Wave W8 (Part 1, with M11 Part 1) and W9 (Part 2).
- **FRED check from Claude's sandbox failed** (2026-10-25: the server answered, then reset every `fredgraph.csv` download). That may be specific to the sandbox. The owner runs one request from the PC before Q10.2 is final (see Q10.2). The worked example keeps the 2026-10-12 values.
- **D32 (sitting 2)** applies: see the next section.

## D32: standard rows for every company, and rules whose evidence is tech-only
**Standard rows (default; strike if you disagree).**
- The Macro page shows every fetched series with its latest value, as-of date, state and the date the state last changed. CPI and M2 also show year-over-year change, with no state.
- Q10.3 adds an optional "+STD": the fed funds rate (DFF) and the unemployment rate (UNRATE), display only, 2 requests.
- Every company's Overview line shows its class ("none" and "not applicable" included), its `macro_exposure_warning` and its last weekly move, whether or not the class is in stress (D10).
- Exposure routing chooses which warnings can fire, never what is shown.

**Tech-only evidence (flagged as D9 failure modes, checked on non-tech names at tuning):**
1. **Policy events.** The agency watch (BIS and presidential documents) and the two topics (tariffs/trade, export controls) come from semiconductor cases: H20 and Proclamation 11002. A non-tech name's policy risk sits with other agencies:
   - FAA for BA (excluded in the MVP for volume);
   - FDA and CMS for pharma;
   - EPA and FERC for utilities;
   - bank regulators for banks.

   Those names read "no policy topic configured" rather than "no exposure". `config/macro_topics.toml` takes an agency list per topic, so the owner can add one without code.
2. **Classes on M04 4a rows.** These work for any filer, but two kinds of company read wrong:
   - **Negative FCF from investment:** capex-heavy growers (AMZN, BA) and regulated utilities read long-duration. For utilities that reading is arguably right, since they are rate-sensitive.
   - **Banks and insurers:** FCF and the gate are not meaningful, and their rate exposure runs the other way (net interest margin). The build reads SIC 6000–6799 as "class not mapped (financials)", never "none".
3. **Move context vs SPY.** A large-cap US benchmark fits poorly for small caps, ADRs and sector-driven names; sector ETFs are deferred (Round 3). Labelled "vs SPY" on every line.
4. **Zones are market-wide, not watchlist-tuned.** The BAA10Y percentile, NFCI > 0, Sahm 0.50 and DGS10 +1 pp come from the sources cited, not from these 16 names. This part needs no flag.
5. **First tests are tech names.** The April 2025 replay and the policy fixture are tech cases. The build adds non-tech fixtures: a regulated utility (negative FCF, long-duration), a regional bank (not mapped), and a Federal Register document for an airline or pharma name with no topic configured.

## Purpose in one paragraph
M10 reports the macro and policy backdrop, which names are exposed to it, and what is on file when a name moves. It serves three parts of the outline:
- "Understand why an asset is or is not moving": item 1 (macro, wars, rates, politics) and items 3–4 ("if you don't know why it moves you have no edge"; "this asset is moving because …").
- "Killswitch" item 3: a ban or rule that changes the idea. M11 owns the killswitch; M10 supplies the events.
- "Analyze the financials" item 5: money supply plus inflation. M10 fetches CPI and M2 for M01's hurdle.

Other parts of "why is it moving" are served elsewhere and only read here: money flows and "late capital chasing the same story" (item 2) by M02's money flow and fund-filing crowding count (D-M02-10, -57); future earnings by the guidance ledger (R19); short squeezes by M07 (outline Ownership item 4); "edge but not moving = early" (item 5) by M01 rule 5 and M11 (R4). "Wars" and "the narrative" have no MVP signal: GPR and narrative tracking are deferred (Round 4); policy events cover sanctions and export rules only.

**No approved revisions exist for M10.** It honours R23 and R4 (M11), M01 rules 4 and 6, D8/D16, D10–D14, D-UI-2 (internal licences), D-M02-12 (logon catch-up), D-M02-42 (market credit spread is M10's) and D-M02-54/55 (macro wording M02 drops is M10's).

**Where the MVP departs from the pack:** the pack was written before the outline was in the repo and treats M10 as a regime forecaster. The outline's M10 section is about explaining moves. So the MVP adds `move_context` (Q10.7) and defers the forecasting and backtest rounds.

## Data already stored that the MVP uses
| Need | Stored in (code path) | Gap |
|---|---|---|
| Ticker signals | `signal` via `src/engine/signals.py` `write_signal` (cik NOT NULL, length 10; `value_text`; migration 0029) | Market readings cannot carry a CIK → new table (Q10.1) |
| Financing dependence, duration proxy | M04 Part 4a rows `survival_gate`, `runway_q`, `maturity_wall` ((12-month debt + 4 × burn) ÷ liquidity), `fcf_burn` (TTM FCF ÷ revenue; the tier cash_burner / capex_funded / self_funding in `value_text`) (`financials/gate_step.py`); `config/company_models.toml` tags (`asset_treasury` MSTR, `fund` ETV, `spac_shell` INFQ before 2026-02-13) | `financing_pressure` is decided (D-M04-25…28), but Part 5 is deferred (D31): the MVP reads the 4a rows instead |
| Policy documents | `fedreg_doc`, `official_theme` (0027/0028), `official/fedreg.py` (no key; searches theme phrases in RULE/PRORULE/NOTICE; stores title, agencies, publication date, abstract ≤ 300 characters) | Agency and presidential-document queries, plus the signing and effective dates (not stored today) → a small extension of the 7b adapter (pack 5.1a) |
| Company text that states an exposure | corpus `section` / `passage` / `passage_fts`: latest 10-K/10-Q (plus M02's year-ago twins), the last 4 earnings 8-Ks and every 8-K filed since the backfill, call turns labelled `call management` / `call analyst` (`calls/transcripts.py`) | Older non-earnings 8-Ks (e.g. NVIDIA's 2025-04-09 H20 8-K) have an `event` row only, with no text: 1–2 SEC requests each if wanted, else the event title |
| Catalysts | `event` (0006), `news_item` / `news_company` / `news_source` (0025, grades A/B/C), `m04_event`, `guidance` | News starts 2026-10 (part 7a) |
| Prices | `price_bar` (keyed by symbol) / `price_fetch` (0012, `prices/store.py`); SPY stored since M09 Part 1 (`BENCHMARK`); completed weeks `technicals/bars.py`; earnings in the window `technicals/earnings.py` | None (internal use only, S68) |
| Credit distress text | M04 4b-lite rows `gc_language`, `covenant_status` (`financials/gate_text_step.py`; warn / fail classes) | None |
| Macro series | — (M04's Ohlson O reads a hand-entered GNPDEF table with 3 years, `financials/distress.py`, D-M04-87) | **New gap DS23:** FRED keyless `fredgraph.csv` (S-new-M10-17), 1 request per series |
| Geography, floating-rate debt | — | DS12 (geography not stored); deferred |

## MVP signals (4)
✓ = may carry weight once D13 weights exist; info = weight 0. Under Q10.8a all four rows are info. "alert" = surfaced under M01 rule 6.

| Signal | value / value_text | Meaning | Inputs | MY | PT | ST | Evidence grade |
|---|---|---|---|---|---|---|---|
| `macro_regime` (`macro_reading`, not `signal`) | value = latest weekly reading; text normal / watch / stress / stale. Composite row: count in stress | State per indicator, each with its own as-of date and the date the state last changed; no single score (pack S1.3) | FRED T10Y3M, DGS10, BAA10Y, NFCI, SAHMREALTIME. CPIAUCSL and M2SL are stored for M01 and carry no state | info | info | info | A; "stale since <date>" when a release is missed |
| `macro_exposure_warning` | text warn / watch / none / not_applicable; class and indicators in `method` | The company's own M04 rows make it sensitive to an indicator that is in stress; "missing: M04 rows missing" when the gate is incomplete (SPCX) | `macro_reading`, M04 4a rows, tag file | info (warning) | info | info | Weakest of A and the M04 row's grade |
| `policy_event_exposure` | value 1; text confirmed / stated / mentioned | A new BIS rule or presidential document on a topic the company's own text names. Stated = an amount or impact sentence; mentioned = risk factors or MD&A only | `policy_event` (Federal Register agency watch), topic lexicon, company passages with a verbatim quote | info (warning; M11 input) | info | info (alert) | A for the document and a filing quote; B for a call quote or an owner confirmation |
| `move_context` | value = weekly excess-return z vs SPY; text catalyst_on_file / no_catalyst_on_file / before_coverage; catalysts in `method` | What the engine knows inside the move window; the owner may add the "because" sentence | `price_bar` (the name and SPY; the chart's Monday-keyed weeks, D-UI-8), `event`, `news_item`, `guidance` changes, `policy_event`, regime and gate state changes | info | info | info (alert on no_catalyst) | A for the move (D-M04-82); with catalysts, the weakest catalyst's grade; the owner's sentence is B |

**Starting rules** (the pack's Round 2 sets the real values at tuning):
- Daily series become weekly (Friday) averages.
- **Watch** = in zone for fewer than 4 weekly readings; **stress** = in zone from the 4th (pack 6.2a). SAHMREALTIME is monthly: 1 reading in zone = watch, 2 = stress.
- **Zones:**
  - T10Y3M < 0. Capped at watch: it is a leading probability, and 2022–24 was a false alarm.
  - DGS10 up ≥ 1.00 pp in 26 weeks.
  - BAA10Y ≥ its trailing 10-year 90th percentile (illus.).
  - NFCI > 0, i.e. tighter than average (S-new-M10-21).
  - SAHMREALTIME ≥ 0.50.
- **Classes** (a name may hold both of the first two; asset-holding replaces them):
  - Credit-sensitive: `survival_gate` warn or fail, numeric `runway_q` < 8 (the gate's warn band, D-M04-32), or `maturity_wall` ≥ 1 (its warn line, D-M04-33); since 4b-lite, also `covenant_status` or `gc_language` at warn or fail (default; strike it if you disagree).
  - Not mapped: SIC 6000–6799 (banks, insurers; D32 flag 2) reads "class not mapped (financials)".
  - Long-duration: TTM FCF < 0 (`fcf_burn` value; Q10.5 may narrow it to the cash_burner tier).
  - Asset-holding: `asset_treasury`.
  - Not applicable: `fund`.
- **Warnings:**
  - Credit-sensitive, with BAA10Y and NFCI both in stress → warn; one of the two in stress → watch.
  - Long-duration, with the rate shock in stress → warn.
  - Asset-holding → watch at most.
  - T10Y3M and SAHMREALTIME warn no company: they show on the Macro page and in the composite only.

## Worked example
**Today** (real FRED values, checked 2026-10-12, S-new-M10-17):

| Indicator | Latest | Zone | State |
|---|---|---|---|
| T10Y3M | +0.99 (2026-10-09) | < 0 | normal |
| BAA10Y | 1.48 (2026-10-08) | ≥ 10-yr p90 (illus.) | normal |
| NFCI | −0.494 (week to 2026-10-02) | > 0 | normal |
| SAHMREALTIME | 0.00 (Sep 2026) | ≥ 0.50 | normal |
| DGS10 26-week change | computed at build | ≥ +1.00 pp | — |

0 indicators are in stress, so `macro_exposure_warning` reads none for every name.

**Classes from M04's real 4a re-run** (`logs/financials_gate_20261013-102901.txt`):

| Company | Gate | runway_q (tier) | fcf_burn | Class |
|---|---|---|---|---|
| RIVN | fail | 5.5 (cash burner) | −59.3% | credit-sensitive + long-duration |
| ORCL | warn | 5.2 (capex-funded) | −40.0% | credit-sensitive + long-duration (tracked tier: rows only, D-M04-80) |
| INFQ | pass | 93.6 (cash burner) | −49.6% | long-duration (no class before 2026-02-13) |
| AMZN | pass | 9.1 (capex-funded) | −1.5% | long-duration (by a hair) |
| BA | pass | 48.7 (capex-funded) | −0.2% | long-duration (by a hair) |
| MSTR | pass, liquidity-only (12-month wall 40M vs liquidity 2,448M) | 373.9 (cash burner) | −5.3% | asset-holding |
| SPCX | incomplete | — | — | missing |
| ETV | not_applicable | — | — | not_applicable |
| GFS | pass | self-funding | positive | credit-sensitive under the 4b-lite default (covenant warn: "breach or default waived or cured", `logs/financials_gate-text_20261013-134918.txt`); none without it |
| AAPL, AVGO, GOOG, INTC, META, MRVL, MSFT, MU, NVDA, TSLA | pass | self-funding | +5.0% to +44.3% | none |

SPCX is also at covenant warn on that log, but its gate is incomplete, so it stays missing. These rows are re-read at build from the stored rows; new 10-Qs since 2026-10-13 may change them. No name has `maturity_wall` ≥ 1 today. AMZN and BA show the proxy's weakness: growth capex, not a duration bet, makes FCF negative (Q10.5b narrows it).

**April 2025 replay** (real values: BAA10Y 1.73 on Apr 2 → 2.02 on Apr 7 and Apr 9; HY OAS 3.42 → 4.61):
- 2.02 may not even reach the 10-year 90th percentile: the 2015–25 window likely holds higher readings (the 2016 and 2020 credit spikes; unverified), so a level-percentile zone may read normal through the whole shock. The build replays it on the fetched series; a credit-sensitive name reads at most watch from a one-week spike.
- A yes/no rule on HY OAS would have warned on a 5-day spike (S86).

**Policy event** (real document; company links illus.):
- **Document:** FR 2026-01052, Proclamation 11002 (Section 232, 25% on advanced logic chips defined by thresholds).
- **Dates:** signed 01-14, effective 01-15, published 2026-01-20. The event date is the earliest (Q10.6a).
- **Topic:** tariffs/trade ("Section 232" and "duty" in the title and abstract).
- **Links:**
  - A 10-Q or call after 01-14 that states an amount or impact → stated. The model is NVIDIA's 2025-04-09 H20 8-K: "up to approximately $5.5 billion" (S-new-M10-31).
  - A risk-factor mention only → mentioned: a banner, never a trip.

**Move** (illus.):
- NVDA's week to 2025-04-11, excess z −2.4 (illus.; re-read from `price_bar` at build).
- Catalysts in the window: the 2025-04-09 8-K (event row, A; its text is not stored) and any BIS documents of that week. News for the window reads before_coverage.
- Result: catalyst_on_file. The owner may write "moving because the H20 licence rule …".

## Cases the rules must handle
1. New value or revision: a new row with the fetch date as vintage; old rows kept. History before our first download is labelled "revisions may leak" (mislead: backfilled NFCI is the revised series).
2. Series deleted, release missed or fetch failed: "stale since <date>", never carried forward; the run continues.
3. Blank or "." value: missing, never zero. Mixed frequencies: each state has its own as-of (release) date.
4. Flicker around a zone (T10Y3M −0.02 to −0.06 in 2025): one episode under persistence.
5. 25-month inversion with no recession (2022–24): T10Y3M capped at watch. Sahm without a recession (Jul 2024, S-new-M10-26): one indicator, cannot warn alone.
6. M04 row missing (SPCX), tracked tier (rows, no alert, D-M04-80), `spac_shell` periods (INFQ before 2026-02-13: no class), fund (ETV: not_applicable).
7. Asset-holding (MSTR): watch at most (mislead: bitcoin swings look like duration).
8. Empty `effective_on` in the API reply: missing (the body text is not stored). Reversal by press release or court (AI Diffusion 2025-05-13; IEEPA 2026-02-20): "as issued; later changes not checked".
9. Rule naming no product (Proclamation 11002) or export-control boilerplate in every risk-factor section: mentioned only; only stated or confirmed links trip.
10. Same action in 8-K, news and the Register: one event, several sources.
11. False keyword match (drones, firearms in BIS lists): agency + type filters, lexicon on title/abstract only, owner confirmation.
12. Move with no stored catalyst: no_catalyst_on_file; window before the news store: before_coverage, never "unexplained".
13. Earnings week: the earnings 8-K is the catalyst; a market-wide day drops out of the excess return.
14. Short history (SPCX prices from 2026-06-12): "insufficient history" below 52 weeks.
15. A catalyst on file is not a cause: only the owner writes "because" (mislead: coincidence read as explanation).
16. Licences: SPY bars internal display only (D-UI-2, S68); BAA10Y is Moody's-derived, its terms checked at build and kept internal meanwhile.
17. Logon run killed at 3 h: idempotent, resumes next run (D-M02-12).
18. First run (Federal Register from 2025-01-01, past moves): a baseline, shown but never alerted (LESSONS: a first scan is not news).
19. Catalyst grade C (97% of Finnhub items, D-M02-59): one event takes the best grade of its sources (case 10); a move whose only catalyst is a C item reads C.

## Deferred to the tuning phase
- **Round 1:** EBP/GSW, Engstrom–Sharpe, regional surveys, IPMAN/IPG3344S (noise before calibration); HY OAS (ICE licence, 3-year window; unless Q10.3b); net liquidity left out per pack 1.2a (no peer-reviewed support).
- **Round 2:** ALFRED backfill, backtest, hit/false-alarm/miss records (need the key and use first).
- **Round 3:** betas, sector ETFs (unstable; ~15 min/day of Tiingo); geographic revenue and floating-rate debt as M04 additions (its note: all axes on Part 7a's read, 0 extra requests per new filing; floating-rate debt in 4a); M04's `rating_action` rows (DS17) and 4b-lite's `covenant_status` as credit-class inputs.
- **Round 4:** `narrative_topic_rise` vs twins, `m10_phrase` capture, EPU/TPU/GPR (the MVP lexicon is the first step).
- **Round 5:** Congress, reversal-status tracking, USTR/ITA/FCC/DoD filters (unverified), FAA ADs for BA (volume).
- **Round 6:** killswitch templates and shared-exposure view (R23) are M11's (pack 6.3a); M04 Q1 evidence row later.

## Questions for the owner
**Q10.1 Where market readings live**
- a) *Recommended.* New tables `macro_series` (series, date, value, vintage_date, source, licence) and `macro_reading`; per-ticker effects go to `signal`. Why: `signal` is keyed by a real CIK (D-M04-74, migration 0029), and 0029 already uses 0000000000 for unresolved rows (pack 1.1a).
- b) A pseudo-CIK 0000000000 in `signal` (collides with that fallback).

**Q10.2 FRED access**
- a) *Recommended if the owner's one-request check returns rows.* Keyless CSV now, storing our own vintages from day one; free key and ALFRED at tuning. Why: no owner action, and the backtest that needs vintages is deferred (S-new-M10-17, -18).
- b) The owner gets a free key now (`FRED_API_KEY` in `.env`), and the build uses the documented API and backfills ALFRED. *Recommended if the check fails*: Claude's sandbox was reset on every `fredgraph.csv` download on 2026-10-25.
- Check (owner, 1 request): `curl.exe -s "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCI&cosd=2026-09-01" > logs\fred_probe.txt`. Rows of dates and values mean the CSV works from the PC (a); an empty file or an error means the key route (b).

**Q10.3 Indicator set**
- a) *Recommended.* T10Y3M, DGS10, BAA10Y, NFCI, SAHMREALTIME, plus CPIAUCSL and M2SL for M01: at most 7 requests a run. BAA10Y is then the market credit spread D-M02-42 assigns to M10. Why: covers curve, rates, credit, conditions and labour; BAA10Y goes back to 1986 (S-new-M10-1, -4, -17, -21).
- b) As a, plus HY OAS for display (internal, 3-year window; the series D-M02-42 names).
- c) The pack's full list (about 10 series, plus EBP and GSW).
- With any option, GNPDEF can be added for 1 request to fill M04's missing Ohlson O years (D-M04-87): answer "+GNPDEF".
- With any option, "+STD" adds the fed funds rate (DFF) and the unemployment rate (UNRATE) as display-only standard rows (D32), 2 requests, no state.
- *Recommended overall:* a + GNPDEF + STD, at most 10 requests a run (MVP_PLAN's "≤ 7 a day" becomes ≤ 10). Weekly and monthly series are fetched only when due.

**Q10.4 Persistence and warning trigger (MY)**
- a) *Recommended.* Stress after 4 weekly readings in zone; a credit warning needs both BAA10Y and NFCI. Why: filters the 2025 flicker and the April 2025 spike (pack 6.2a, S86).
- b) One indicator, immediately.
- c) Owner-set per indicator in a toml.

**Q10.5 Which names an indicator touches**
- a) *Recommended.* Classes from M04's 4a rows, as in Starting rules (long-duration on any negative FCF: RIVN, ORCL, INFQ, AMZN, BA). Why: rows already built on stored data (D-M04-31…33, D31); investment-driven negative FCF is also distant cash flow (S-new-M10-9).
- b) As a, but long-duration only for the cash_burner tier (RIVN, INFQ; MSTR stays asset-holding), dropping capex-funded AMZN, BA, ORCL.
- c) Wait for Part 5's `financing_pressure`: no credit warnings in the MVP.
- d) The owner tags classes in a toml.

**Q10.6 Policy events**
- a) *Recommended.* Agency watch on the 7b adapter: BIS and `PRESDOCU`, about 2–4 requests a day. Topics come from an owner-approved `config/macro_topics.toml` (tariffs/trade, export controls). Links come from the company's own text (stated / mentioned). The owner confirms on the Macro page, with no queue kind (the page list is the D8 review place). The event date is the earliest stated date (pack 5.3a). Why: one adapter and one budget, and publication lagged 6–12 days (pack 5.1a, 5.3a; S94, S-new-M10-30).
- b) As a, plus one weekly `m10_macro` item inside M02's 10-a-week cap.
- c) Defer policy events.

**Q10.7 Move context (the outline's "why is it moving")**
- a) *Recommended.* Include it on the stored SPY bars (M09 Part 1). A weekly excess move with |z| ≥ 2 vs the name's own 52 completed weeks (`technicals/bars.py`) lists the stored catalysts (earnings via `technicals/earnings.py`, plus news, 8-K events, guidance changes, policy events, regime and gate changes); the owner may write the sentence. Why: outline M10 items 3–4; every input is already stored, so it costs 0 requests (S68).
- b) Defer (the pack's design).
- c) Include it on raw returns, without SPY.

**Q10.8 Weight before any backtest**
- a) *Recommended.* All rows info (weight 0); warnings are shown and kept for M11. Why: many predictors fail out of sample (S-new-M10-5, -6), and there have been only about 8 recessions (S-new-M10-25).
- b) A small MY weight for `macro_exposure_warning`.

## Build parts
**Part 1: macro series, regime, exposure, moves**

| Item | Plan |
|---|---|
| Code | `src/engine/macro/`: `fred.py` (keyless CSV or key per Q10.2, U7 budget, vintages; shared with M12), `regime.py`, `exposure.py`, `moves.py` (reuses `technicals/bars.py` and `technicals/earnings.py`), `step.py`; `scripts/run_macro.py` |
| Tables | `macro_series`, `macro_reading`, `move_note`; migration `0045_m10_macro`, D-STO-35, D-UI-44, DS23 |
| Review kinds | none |
| UI | New Macro page (states, as-of dates, last change, composite, licence label); one M10 line per company on the Overview tab (class, warning, last move with catalysts, sentence box) |
| Refresh | Local step after `prices_step`; FRED once a day, weekly and monthly series only when due |
| Live check | `uv run python scripts/run_macro.py regime`: up to 10 FRED requests (Q10.3), SPY already stored, 0 SEC, under 2 min; `--no-fetch` for re-runs |
| Fixtures | Hand-built CSVs from the pack's real values (T10Y3M 2022-10…2025-09, BAA10Y and HY OAS Apr 2025, NFCI); synthetic bars with SPY; M04 rows for RIVN, AMZN, MSTR, ETV, SPCX, GFS (covenant warn); D32 non-tech cases: a regulated utility, a regional bank |
| Depends on | M04 4a (built); not on 4b-lite or 8a |

**Part 2: policy events and stated exposure**

| Item | Plan |
|---|---|
| Code | Agency/type query in `fedreg.py`; `macro/topics.py` (lexicon, verbatim quotes, stated vs mentioned); `macro/policy.py` |
| Tables | `policy_event` (three dates, agency, type, status, topics, grade, source_ref) and `policy_link` (cik, level, quote, passage_id, owner_confirmed_at); migration `0047_m10_policy`, D-STO-37, D-UI-46, next free D-M02 for the `fedreg.py` extension |
| Config | `config/macro_topics.toml` |
| UI | Event list with link confirm/reject on the Macro page; policy rows on Overview; policy events become move catalysts |
| Live check | `run_macro.py policy`: Federal Register from 2025-01-01, 2 agency queries, about 6–10 requests, 0 SEC, under 3 min |
| Fixtures | documents.json with FR 2026-01052 and 2025-00636; passages with a quantified sentence and with boilerplate |
| Depends on | M02 7b (built) and Part 1; M11 reads both parts later |

## Open risks
- `fredgraph.csv` is a graph download, not the documented API; terms unverified, and Claude's sandbox was reset on every download on 2026-10-25. The owner's one-request check settles Q10.2; fallback: free key (Q10.2b).
- Zones and the 10-year percentile are untested starting values (LESSONS: calibrate a cut-off on known cases first); the April 2025 replay is the first test.
- M04 classes are proxies and labelled so (AMZN, BA by a hair; Q10.5).
- Presidential documents (hundreds a year) may flood the Macro page; topic filters first, FAA excluded.
- Numbers are pre-assigned in MVP_PLAN (0045/0047, DS23); a W6 or W7 part that needs an unplanned migration moves them up by one (MVP_PLAN rules).
- M11 has no design: warnings appear only on the pages until M11 reads them (M01 rule 4).

## Check notes (2026-10-13)
- **Numbers (fixed):** the classes table showed "15 passes … read at build (AMZN −8.2% in the 4a fixture)" and counted MSTR twice. The cited log already holds every value: replaced with the real `runway_q`, tier and `fcf_burn` for all 19 names (AMZN −1.5%, BA −0.2% fall in long-duration; INFQ −49.6%; no wall ≥ 1).
- **Numbers (fixed):** the April 2025 replay claimed RIVN "reads watch"; 2.02 may not reach a 10-year 90th percentile at all, and RIVN's 2025 gate state is not stored. Reworded as a build-time replay; the percentile doubt is marked unverified.
- **Data reality (fixed):** company text overclaimed "8-K exhibits … 0 requests": only the last 4 earnings 8-Ks and 8-Ks since the backfill have text; the H20 8-K is an `event` row only. `fedreg_doc` stores no signing or effective dates and no body text (case 8 changed). `price_bar` has no cik column (the NULL cik is `price_fetch`). Added the `fcf_burn` tier in `value_text` and the `maturity_wall` formula. All other named tables, columns, files and config tags verified in the migrations and `src/`.
- **Sources (fixed):** BAA10Y's 1986 start is S-new-M10-17, added to Q10.3a's cite; BAA10Y's Moody's licence was attributed to S68 (Tiingo only), now "checked at build".
- **Binding decisions (fixed):** D-M02-42 names HY OAS as M10's market credit spread: Q10.3 now says BAA10Y fills that role under a, HY OAS under b. Runway < 8 and wall ≥ 1 now cite D-M04-32/-33 (the gate's own warn lines). Q10.1's reason updated: `signal` is keyed by CIK (D-M04-74) and 0029 already uses 0000000000 as its unresolved fallback. No question re-asks a decided point.
- **Outline fit (fixed):** added which outline "why is it moving" items are served elsewhere (item 2 crowding by M02, future earnings R19, short squeezes M07, item 5 by M01 rule 5/M11) and that "wars" and "the narrative" have no MVP signal.
- **Overlap (fixed):** M04's hand-entered GNPDEF table (3 years) can be filled by M10's fetcher for 1 request (optional "+GNPDEF" in Q10.3); `rating_action` (DS17) and 4b-lite `covenant_status` listed as later credit-class inputs; `guidance` changes added as move catalysts.
- **Cases (added):** 18 first run is a baseline (LESSONS); 19 grade-C catalysts. Warnings: T10Y3M and SAHMREALTIME warn no company (was implicit).
- **Questions (changed):** Q10.5 gains b) long-duration only for the cash_burner tier, because the real data put capex-funded AMZN and BA in long-duration by a hair; old b/c become c/d. Q10.6a notes the Macro page list as the D8 review place.
- **MVP discipline:** 4 signals, 8 questions, 2 parts, live checks under 3 min with 0 SEC requests: no change. D13 fields (cik key, value vs value_text, missing rows, grade, MY/PT/ST) were already right; a missing row for SPCX was made explicit. The body is about 20k characters without these notes, above the 8–15k target; the added real-data table and cases account for most of it.

## Refresh notes (2026-10-25, sitting 4)
- SPY, the week reader and the earnings-in-window helper are built (M09 Part 1), so Q10.7a costs 0 requests and reuses them. 4b-lite's `covenant_status` and `gc_language` move from Round 3 into the credit class as a default, which puts GFS in the class (covenant warn on the 2026-10-13 log). SIC 6000–6799 reads "class not mapped".
- D32 section added: standard rows, "+STD" (DFF, UNRATE) in Q10.3, five tech-only flags, and non-tech fixtures.
- Q10.2 depends on the owner's one-request check, because Claude's sandbox could not download `fredgraph.csv`. The FRED values in the worked example stay those checked on 2026-10-12.
- Numbers from MVP_PLAN: 0045/0047, D-STO-35/37, D-UI-44/46, DS23. The eight questions and their order are unchanged.
