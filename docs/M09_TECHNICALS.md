# M09 — Technicals

Status: MVP design decided 2026-10-13 (sitting 1, D-M09-1…8); build parts 1–2 below · Updated: 2026-10-13 · Outline headings: Technical analysis (items 1–4; "comes second — guides when to invest") · Depends on: M00 (prices D-UI-8, D13 writer), M01 (rules 1, 3, 7; trend filter; entry zone), M04 Part 4a (`survival_gate`, `filing_status`), Part 8a (`cvd_state`, soft) · Sources: S01, S12, S68, S-new-M09-1…14 (provisional IDs from `docs/M09_DESIGN_PACK.md` "New sources"; numbered into SOURCES.md at Part 1)

Research: `docs/M09_DESIGN_PACK.md`; MVP cut: `docs/mvp/M09_MVP_BRIEF.md`; cross-module plan: `docs/mvp/MVP_PLAN.md`. Parameters are frozen in `config/technicals.toml` with version `v1` written into `method`; values marked † are starting values, calibrated by backtest at tuning. Missing data stays missing, never zero (D-M04-9). Research signals only; M09 never fires a buy on its own and has no technical exit signal (D16).

## Purpose
When to act on a name the fundamentals already favour: depth in M01's σ band (D27), trend context, momentum (PT) and short-term reversal (ST). Binding: A4 (reversal ST, momentum PT, fundamentals-led MY), R3 (mean reversion only on qualified names), R17 ("80% dead or dying" is a heuristic), D27 with M01 rules 1, 3, 7 and D-M01-5/-6, R20 (M12 reads a weak or sideways regime), D10, D13 with D-M04-9 and D-M04-74, D14 (prices grade A, D-M04-82).

## Inputs
| Data | Source (stored in; code) | Grade | Refresh |
|---|---|---|---|
| Daily adjusted OHLCV, dividend, split | Tiingo → `price_bar` (0012); `prices/store.py` | A (D-M04-82) | Logon refresh (tracked names: 3-day rotation, D-M02-12) |
| Symbol → CIK, fetch state, stale after 5 days | `price_fetch.cik`, `STALE_AFTER_DAYS`; symbol map in `prices_step` | — | Same |
| Completed weekly bars | new `technicals/bars.py` (Part 1) on `price_bar`; `bars()` includes the partial week, so it is not used | A | Derived |
| SPY (benchmark, no CIK, no D13 rows) | Tiingo, added to `prices_step` (D-M09-6) | A | 1 request a day |
| Earnings 8-Ks | `event` (0006): `category = 'earnings'`, `filed`, `accepted_at` | A | Logon refresh |
| M04 gate, filing status, CvD | `signal` via `signals.latest_signal`: `survival_gate`, `filing_status`, `cvd_state` (8a; missing until built) | per M04 | Per M04 run |
| Model tags | `config/company_models.toml` (INFQ `spac_shell` before 2026-02-13; ETV `fund`; MSTR `asset_treasury`) | Owner | On edit |

## Signals out
Every row: `cik` key (ticker for display, D-M04-74), `module_id = "M09"`, numbers in `value`, states in `value_text` (D-M04-9), grade A, `source_ref` = "Tiingo adj_close <date>", `as_of` = the last completed week's final session (US Eastern, D-SEC-16), one row set per completed week from the first run (no history backfill; the chart computes history on the fly). One computation serves every profile (D10). ✓ = may carry weight once D13 weights exist (whether a backtest must come first is a tuning question); info = weight 0.

| Signal | value / value_text | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| `band_z` | z of ln(close) vs the 20-week mean of ln(close), signed, uncapped / `below_2`, `below_1`, `inside`, `above_1`, `above_2` | Depth in M01's band, the D27 trigger (D-M09-2); `pullback_sigma`, 20-week high, qualification label and R17 note in `method` | ✓ lead (timing) | info | info |
| `price_band` | 20-week mean of the close (price level); σ of the close and the −2σ, −1σ, +1σ, +2σ levels and z of price in `method` | Price-level σ band for the chart overlay (owner amendment, D-M09-2): information and display, never a trigger, never voted | info | info | info |
| `trend_state` | +1 / 0 / −1 / `up`, `flat`, `down`; "pending flip", `ma_distance` %, slope and falling-knife label in `method` | Close vs the 40-week MA plus its 4-week slope (D-M09-5) | ✓ context (M01 trend filter) | ✓ | info |
| `mom_12_1` | return / `positive`, `negative`; 52-week-high ratio and SPY's 12-1 in `method` | 12-1 time-series momentum, PT lead (A4) | info | ✓ lead | info |
| `rev_1m` | z = 4-week log return ÷ (2 σ_w) / `extended_up`, `extended_down` (\|z\| ≥ 2†), `normal`, `news_move` | Short-term reversal candidate, ST lead (A4); "turnover not checked (deferred)" on every row | info | info | ✓ lead |

Missing rows: "missing: insufficient_history (n/N)", "missing: stale bars", "missing: shell period (before 2026-02-13)". A symbol without a CIK (SPY) gets no rows.

## Timeframe parameters
One computation for every profile; profiles differ in weight (above). Weekly bars (M01 default).

| Parameter | Value (v1) | Bars needed |
|---|---|---|
| Band window (`band_z`, `price_band`, `pullback_sigma`) | 20 completed weeks | 20 |
| Band zones | ±1σ, ±2σ (D27; depth uncapped) | — |
| Trend MA; slope; flip | 40-week MA; 4-week change of the MA; position flips after 2 consecutive closes | 45 |
| Momentum | close 4 weeks ago ÷ close 52 weeks ago | 53 |
| Reversal | 4-week log return; σ_w from the 26 weeks before the window; \|z\| ≥ 2† | 31 |

## Rules
1. **Completed bars only.** The partial current week, or a tracked name's week whose last session is not yet fetched, is excluded; the older `as_of` is shown. Missing days are never filled; stale bars (over 5 days) → "missing: stale bars".
2. **Band (D27, D-M09-2).** `band_z` = (ln close − mean of ln close over 20 weeks) ÷ σ of ln close over the same weeks. `pullback_sigma` = ln(close ÷ 20-week high) ÷ σ_w (weekly log returns, 20 weeks), always shown beside it. `price_band` = 20-week mean of the close ± 1σ / ± 2σ of the close: stored for the overlay, never a trigger.
3. **Qualification label (R3; D-M01-5, -6; D-M09-4)** from `src/engine/m01_rules.py` (shared with M11, M12): gate pass or warn, no overdue filing and CvD not STRUCTURAL_DECLINE or CYCLE_PLUS_DAMAGE → qualified; gate fail, incomplete or not applicable (ETV `fund`, D-M04-35) → "not qualified", value still shown with the R17 note; `cvd_state` missing → "qualification incomplete"; tracked names → "qualification: not covered by M04 (D-M04-80)". MSTR: no special rule (D-M04-8). The label is context, never a deciding input of the grade.
4. **Beyond 2σ (M01 rule 7):** "stronger" only with gate pass or warn and CvD = CYCLICAL_TROUGH; any other or missing CvD → warning, no added strength.
5. **Tops (D-M09-3):** `above_1` / `above_2` are labelled "upper extreme — information" for M12; never a sell signal (D16).
6. **Trend (D-M09-5):** position above or below the 40-week MA flips after 2 consecutive weekly closes ("pending flip" after one); state `up` = above and MA rising, `down` = below and MA falling, otherwise `flat` (slope tolerance in config†). Falling-knife label when `mom_12_1` < 0 and the trend is `down`. Context and warning only; never blocks.
7. **News moves.** An earnings 8-K inside the `rev_1m` window, or the session after an after-close filing (`accepted_at`), → `news_move`, "drift expected" (Chan 2003, S-new-M09-3); Tesla's deliveries report carries Item 2.02 and counts (D-M02-23). The earnings-in-window helper is shared with M10 and M12 (MVP_PLAN item 3).
8. **Corporate actions.** A dividend or split refetch rewrites adjusted history; the current week is recomputed, older rows keep the basis named in `method`.
9. **R17 note (D-M09-7)** under any `below_*` zone; repeated `below_2` weeks in a decline are shown each week with the falling-knife label (cooldown deferred).
10. **SPY (D-M09-6):** SPY's 12-1 and trend go into `method` on `mom_12_1` and `trend_state`; SPY missing → "missing: SPY not stored" in `method`.

## Failure modes
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| σ of price level | Inflated by a trend; misses pullbacks in uptrends (MU 2026), fires late in crashes | Trigger on log price; `pullback_sigma` beside it; price-level band display only (D-M09-2) |
| σ bands | Fat tails break normal-model bands more often (Cont 2001, S-new-M09-10) | "normal-model band; hit rates uncalibrated"; backtest at tuning |
| Band trigger in a decline | Fires week after week (falling knife, MSTR Nov 2025 → Jun 2026) | Qualification label, CvD gates (M01 rules 3, 7), falling-knife label |
| `qualified` | Quarterly fundamentals stale against weekly prices; CvD missing until 8a | As-of shown; "qualification incomplete" (D-M09-4) |
| Weekly bars | Partial current week used as a closed bar | Completed-week reader (rule 1) |
| Short history | Windows filled or zeroed (SPCX, INFQ shell) | "insufficient_history (n/N)"; shell cut-off |
| Price vs 40-week MA | Whipsaw near the MA; lags at turns; "up" to the top of a parabolic run | 2-close flip, slope, `ma_distance` (D-M09-5) |
| Trend rules | Data snooping; fail out of sample and after costs (S-new-M09-7) | Context only; parameters frozen, `v1` in `method` |
| 12-1 momentum | Crashes when a falling market rebounds (S-new-M09-9) | Falling-knife label; `market_regime` deferred |
| 1-month reversal | Becomes continuation in high-turnover large caps (S-new-M09-2) | "turnover not checked (deferred)" on every row |
| Any price move | An earnings move read as noise | `news_move` (rule 7) |
| 52-week high | Old peak becomes an anchor | Momentum context in `method`, never a target |
| R17 base rate | Read as a forecast for one stock | Population base rate with sources (D-M09-7) |
| Literature effects | Smaller after publication; cross-sectional evidence, our use is time-series (S-new-M09-6) | Labelled literature, not forecasts |
| Adjusted-price recompute | Old values change after a dividend or split | Rule 8 |
| Profile switching | Owner switches timeframes until a signal appears | Decisions log the profile (D12) |
| SPY as the market | One index stands in for the market; ETF ≠ index TR | Labelled proxy (M01) |

## Decisions
- D-M09-1 (2026-10-13, sitting 1, Q09.1a): the MVP's four signals, one lead per horizon: `band_z` (MY lead), `trend_state` (MY context, PT ✓), `mom_12_1` (PT lead), `rev_1m` (ST lead). Why: A4 is binding (S12; S-new-M09-1, -3, -5, -8) and all four compute locally from stored prices (D31).
- D-M09-2 (2026-10-13, Q09.2a **with owner amendment**): D27's σ is the z of ln(close) against the 20-week mean of ln(close), with `pullback_sigma` shown beside it; the backtest picks at tuning; M01's rule and "20-week mean ± σ" entry zone are unchanged, and M12's add zone (Q12.6) uses the same σ. **Amendment:** the engine also computes and stores σ levels on the price level (20-week mean of the close ± 1σ / ± 2σ of the close, `price_band`) so a chart overlay can show the bands on the price; these are information and display, not a second trigger. Why: log price stays inside M01's approved band while MU's 2026 pullbacks show σ of levels inflated by trend (S-new-M09-10); the owner wants the familiar price-level band on the chart. Applies D27, M01 rule 7.
- D-M09-3 (2026-10-13, Q09.3a): `band_z` is signed; `above_1` and `above_2` are labelled "upper extreme — information" for M12. Why: outline TA 3 asks for tops (calls) and bottoms (puts); R20 (modified) keeps the call window regime-based and signal-only; D16.
- D-M09-4 (2026-10-13, Q09.4a): nothing extra covers the gap until Part 8a writes `cvd_state`: the label reads "qualification incomplete" (gate and filing status shown); no new review kind. Why: 8a builds in W1 (D31) and no strength is granted before weights exist; applies R3, D-M01-5, -6.
- D-M09-5 (2026-10-13, Q09.5a): the 40-week trend is context and warning only; position flips after 2 consecutive weekly closes and the MA slope sets `up`, `flat` or `down`; falling-knife label when `mom_12_1` < 0 and the trend is down; it never blocks. Why: trend rules fail out of sample and after costs (Bajgrowicz & Scaillet 2012, S-new-M09-7); warnings only (D16); M01 rule 3 unchanged.
- D-M09-6 (2026-10-13, Q09.6a): SPY added as a benchmark symbol in `prices_step` (no CIK, no D13 rows): one full-history request, then 1 Tiingo request a day, within 500 symbols a month (S68, D-UI-19). It feeds SPY's 12-1 and trend into `method` and is M01's "S&P 500 total return" proxy for M11 (R5, labelled proxy); shared with M10 (Q10.7a) and M12. Recorded as D-UI-33 at Part 1.
- D-M09-7 (2026-10-13, Q09.7a): R17's warning uses measured base rates: "decline risk: about 40% of Russell 3000 stocks since 1980 suffered a permanent fall of 70% or more from peak (57% in IT; JPM 2014); 58% trailed T-bills (Bessembinder)". Why: no measured source reaches 80% (S-new-M09-12, S01); applies R17.
- D-M09-8 (2026-10-13, Q09.8a): **DESIGN Q2 settled for the MVP:** M01's σ band is the "augmented trading range" the outline lets us create; a named range is chosen at tuning from a chart mock-up of the candidates on stored data. Why: no standard definition was found (pack Round 5; S-new-M09-7, -13).

## Deferred to tuning
- R1: `mom_12_7`, `rel_mom_spy`, 52-week-high ratio as own signals; turnover context on `rev_1m` and `turnover_pctile`; `news_context` from `news_item`; industry momentum; M02's L7 customer-to-supplier return lead (S-new-M09-2, -4).
- R2: `market_regime` and panic with SPY + FRED VIX (M10's FRED client, S-new-M09-9, -14); ST on daily bars (10/50-day, `rev_1w`; needs M01's ST column).
- R3: volatility panel (Yang–Zhang, ATR14, `vol_regime`) and empirical band; per-stock band calibration and outline TA 3's MA length (backtest; S-new-M09-10, -11).
- R4: cooldown, trigger log, `m09_qualify` review kind.
- R5: `range_state` (the named range, D-M09-8).
- R6: state-flip digest; walk-forward backtest, strength per signal and whether a backtest gates weight (pack 6.3); PT/ST rows for M01.
- Exit side of "determine entry/exit points": no technical exit signal in the MVP; exits stay M01 rule 4 and M11 (D16).

## Build parts
Pre-assigned in `docs/mvp/MVP_PLAN.md` (wave W2/W3, worktree side); parts of one module never run in parallel. Part decisions continue at D-M09-9.

**Part 1: Technicals compute** — branch `m09-part1`, wave W2 (worktree; rebased on main after M07 Part 1 merges), no migration expected (if one is needed it takes the next number at merge, MVP_PLAN rule), D-UI-33 (SPY benchmark symbol), DS8 row (SPY).
- Code: `src/engine/technicals/bars.py` (completed-week reader, US Eastern dates, shell cut-off; shared with M10, M12), `bands.py` (log band, `pullback_sigma`, price-level band — one function for the stored row and Part 2's overlay), `signals.py` (the five rows), `src/engine/m01_rules.py` (M01 rule readers 1, 3, 4, 7 from M04 rows; shared with M11, M12), the earnings-in-window helper (shared with M10, M12), `step.py` (local pass after the M04 and M07 local steps, short write transactions), `config/technicals.toml` (`v1`); SPY in `prices_step`; owner script `scripts/run_technicals.py signals [--no-fetch]`.
- Review kinds: none. Docs: this file, DATA_SOURCES DS8 (SPY).
- Fixtures: synthetic series (steady trend, crash, partial week, missing days, dividend refetch, SPCX-length history, INFQ shell cut-off); MSTR checkpoints (170.50 on 2025-11-21; 82.31 on 2026-06-26: `band_z` −2.66, z of price −2.22, `pullback_sigma` −6.83) as known-answer tests; earnings `event` rows; M04 `signal` rows for each gate and CvD state, including missing; a symbol without a CIK.

**Part 2: Technicals tab and chart overlays** — branch `m09-part2`, wave W3, no migration, D-UI-35 (Technicals tab, overlays). Mock-up first on scratch data (D-UI-4, port 8799).
- UI: company tab "Technicals": per profile, the signals with value, zone or state, as_of, `method` on hover, missing reasons, the M04 reading line and the R17 note under any `below_*` zone. Weekly chart overlays: 40-week MA and the **price-level ±1σ / ±2σ bands** from `price_band` (D-M09-2 amendment; history computed on the fly by `bands.py`, latest week equal to the stored row). The Overview signal list gains the M09 rows.
- Fixtures: tab render tests including missing rows (D-UI-7).

## Live checks (owner runs, sends the log)
- Part 1: `uv run python scripts/run_technicals.py signals` (`--no-fetch` skips SPY): 0 SEC, 1 Tiingo request (SPY's first fetch), under a minute; one line per name (values, zones, `price_band` levels, as_of, missing reasons) checked against MU 2026-03-27 / 2026-07-31 (`band_z` +0.32 / +0.43, `pullback_sigma` −2.01 / −2.43), MSTR 2026-06-26 and SPY's trend weeks (2026-10-05 `up`; 2026-03-23 `flat`) from the pack (Yahoo vs Tiingo may differ slightly).
- Part 2: the owner runs the app on the real DB and comments; 0 requests.

## Open questions
- Storage of the price-level bands: one info row `price_band` per completed week (levels in `method`, overlay history computed on the fly) is the default; if the Part 2 mock-up needs stored history, a small table takes the next migration number at merge.
- Band choice (log z vs `pullback_sigma`) and every † value: backtest at tuning.
- PT and ST columns and weights: M01 open question.
- The named "augmented trading range" (DESIGN Q2 beyond the MVP): chart mock-up at tuning (D-M09-8).
