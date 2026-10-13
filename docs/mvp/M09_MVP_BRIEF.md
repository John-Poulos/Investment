# M09 Technicals — MVP brief
**Decided 2026-10-13 → docs/M09_TECHNICALS.md** (D-M09-1…8; Q09.1a–Q09.8a, Q09.2a with the owner's price-level σ band amendment). Kept as the sitting record.
Updated 2026-10-13 · Source: docs/M09_DESIGN_PACK.md (research) · Status: for owner decision (one sitting)

Research signals only, not advice. Nothing here is decided until you answer (D7). Answers become D-M09-1 onward.

## Purpose in one paragraph
M09 says when to act on a name the fundamentals already favour: the outline's "Technical analysis comes second — guides when to invest" and Technical Analysis items 1 (don't buy because it's oversold; R17), 2 (augmented trading range; Q2), 3 (mean reversion at 1–2σ from a running average, "to aid in selling calls at tops and selling puts at bottoms") and 4 (confluence: core's D13 score combines modules; M09 supplies inputs and never fires a buy on its own). `ma_distance` (in `method`) shows how stretched a run is, for the outline's "don't chase after the initial move".

**Binding:** A4 (reversal ST, momentum PT, fundamentals-led MY) · R3 (mean reversion only on qualified names) · R17 ("80% dead or dying" is a heuristic) · D27 with M01 rules 1, 3, 7 (1–2σ triggers, depth uncapped; beyond 2σ stronger only with CvD = CYCLICAL_TROUGH and a gate pass or warn, D-M01-5; first entry needs gate pass or warn, no overdue filing, CvD not STRUCTURAL_DECLINE or CYCLE_PLUS_DAMAGE, D-M01-6) · R20 (M12 reads a weak or sideways regime) · D10, D13 with D-M04-9 and D-M04-74 (cik key), D14 (prices grade A, D-M04-82), D16. **M04 settles:** MSTR is `asset_treasury`, liquidity-only gate, CvD runs (D-M04-8); `qualified` reads `survival_gate` and `cvd_state` per D-M01-5 (M04_BUILD_LOG "Notes for other modules' reviews"); gate "not applicable" reads as not-pass (D-M04-35); tracked names get no M04 rows (D-M04-80).

**Departures from the pack** (written before the outline was in the repo): tops as well as bottoms (Q09.3); the Q2 sentence is now quoted (Q09.8); the outline's "what range for that average is ideal" → M01's 20-week mean for now, calibrated at tuning.

## Data already stored that the MVP uses
| Data | Where (code) | Use |
|---|---|---|
| Daily adjusted OHLCV, dividend, split | `price_bar` (engine 0012, keyed by symbol), written by `prices/store.py` | All four signals |
| Symbol → CIK, fetch state, stale after 5 days | `price_fetch.cik` (NULL allowed), `STALE_AFTER_DAYS` in `prices/store.py`; the refresh's symbol map in `prices_step` | D13 key (cik, D-M04-74); stale label |
| Monday-keyed weekly bars | `prices/store.py` `bars()`. It includes the partial current week, so M09 needs a completed-week reader | Weekly series |
| Earnings 8-Ks | `event` (engine 0006): `category = 'earnings'`, `filed`, `accepted_at` (watchlist and tracked) | Earnings-move label on `rev_1m` |
| M04 gate, filing status, CvD | D13 `signal` (0029 rebuild), read with `signals.latest_signal`: `survival_gate` (Part 4a), `filing_status` (Part 1a), `cvd_state` (Part 8a, **not built yet**) | Qualification label |
| Model tags | `config/company_models.toml` (MSTR `asset_treasury`, ETV `fund`, INFQ `spac_shell` before 2026-02-13) | Shell-period cut-off; fund reading |
| Universe; D13 writer | `config/watchlist.toml` + tracked tier (3-day rotation, D-M02-12); `signals.write_signal` (cik required, `value_text`, `missing=`, `info`; D-M04-9) | Names computed; output (pack 6.4's companion table not needed) |

**Not stored (gaps, with cost):** SPY — 1 Tiingo symbol of the 480 a month, one full-history request then 1 a day (S68, D-UI-19; Q09.6) · VIX (FRED VIXCLS) — 1 request a day plus a new FRED client, which the M10 and M12 briefs also propose (`macro/fred.py`); deferred · analyst revisions — not free (M08) · intraday and implied volatility (DS5). **Stored but unused in the MVP:** turnover inputs (`price_bar` volume; M04's `cover_shares` / `shares_cover`, class-summed for GOOG, META, MSTR, SPCX, core and promoted only, D-M04-2) · `news_item` (from October 2026 only).

## MVP signals (4)
One computation serves every profile (D10). ✓ = may carry weight once core D13 weights exist (M04's convention); whether a backtest must come first is a tuning question (pack 6.3). info = weight 0.

| Signal | value / value_text | Meaning | Inputs | MY | PT | ST | Grade rule |
|---|---|---|---|---|---|---|---|
| `band_z` | z (signed, uncapped); text `below_2` / `below_1` / `inside` / `above_1` / `above_2` | Depth from the 20-week mean, the M01 band (outline TA 3; D27) | 20 completed weekly adjusted closes. `method` also carries `pullback_sigma`, the 20-week high and the qualification label | ✓ lead (timing) | info | info | A (Tiingo closes). The M04 label is context, never a deciding input |
| `trend_state` | +1 / 0 / −1; text `up` / `flat` / `down`, "pending flip" in `method` | Close vs the 40-week MA plus the MA's 4-week slope; flips after 2 closes (Q09.5) | 45 weekly closes (pack: 44; one more for the 2-close flip); `ma_distance` %, slope and the falling-knife label in `method` | ✓ context (M01 trend filter) | ✓ | info | A |
| `mom_12_1` | return; text `positive` / `negative` | 12-1 time-series momentum, PT lead (A4; S12, S-new-M09-5) | Close 4 weeks ago ÷ close 52 weeks ago (53 bars); 52-week-high ratio on daily adjusted closes and SPY's 12-1 (if Q09.6a) in `method` | info | ✓ lead | info | A |
| `rev_1m` | z = 4-week log return ÷ (2 σ_w); text `extended_up` / `extended_down` (\|z\| ≥ 2, starting value in config) / `normal` / `news_move` | Short-term reversal candidate, ST lead (A4; S-new-M09-1, -3) | 4-week return; σ_w from the 26 weeks before the window (31 bars); earnings 8-K in the window → `news_move` ("drift expected", Chan 2003) | info | info | ✓ lead | A |

- **Key:** `cik` from the symbol map (watchlist, promoted and tracked names carry one); a symbol without a CIK (SPY) gets no D13 rows.
- **Missing rows:** "missing: insufficient_history (n/N)", "missing: stale bars", "missing: shell period (before 2026-02-13)".
- **`as_of`** = the last completed week's final session (US Eastern dates, D-SEC-16). One row set per completed week from the first run; no history backfill into `signal` (the chart computes history on the fly).
- **`source_ref`** = "Tiingo adj_close <date>". **Parameters:** frozen in `config/technicals.toml`, version `v1` written into `method`.

## Worked example
Every figure below is from the pack: Yahoo weekly adjusted closes (grade "other"), read 2026-10-12. All of them get recomputed from `price_bar` at build. "illus." marks values that are not computed.

| Name, week ending | Close | `band_z` (log price) | z of price (M01 as written) | `pullback_sigma` | Other |
|---|---|---|---|---|---|
| MU 2026-03-27 | 357.02 | +0.32 `inside` | +0.24 | −2.01 | 20-week high 427.92, −16.6% |
| MU 2026-07-31 | 823.03 | +0.43 `inside` | +0.30 | −2.43 | 20-week high 1133.82, −27.4% |
| MSTR 2025-11-21 | 170.50 | not in pack (recomputed at build) | −2.24 | — | Then fell a further 51.7% |
| MSTR 2026-06-26 | 82.31 | **−2.66 `below_2`** | −2.22 | −6.83 | 53.2% below the 40-week MA (175.85); `down` if the MA was falling (slope not in pack, illus.); falling-knife label if 12-1 < 0 (illus.) |
| MSTR 2026-10-09 | 154.34 | — | — | — | `mom_12_1` −57.0% (`negative`); last 4 weeks +17.8% → `rev_1m` zone depends on σ_w (not in pack) |
| MU 2026-10-09 | 1029.00 | — | — | — | `mom_12_1` +437.6%; 52-week-high ratio 0.908 on weekly closes, 0.820 on the intraday high |

**MSTR, week ending 2026-06-26, as one D13 row (MY):**
- `cik` 0001050446, ticker MSTR, `band_z`, value −2.66, `value_text` `below_2`, grade A, `source_ref` "Tiingo adj_close 2026-06-26".
- `method`: "band_z v1; pullback_sigma −6.83; M04 reading: gate <state> (illus.), cvd_state missing: Part 8a not built → beyond 2σ shown as a warning, no added strength (D27, D-M01-5); decline-risk note (R17)".
- What happened next: the price rose 87.5% by 2026-10-09. The November trigger, by contrast, would have caught the knife. This is the case the gates exist for.

**SPY trend, if Q09.6a:**
- Week of 2026-10-05: 778.57 against the 40-week MA of 721.29 (+7.9%), slope +1.3% → `up`.
- Week of 2026-03-23: 630.89 against 656.64 (−3.9%). That is the second close below the MA, so the position flips, but the MA was still rising (+1.0%) → `flat`, not `down`. The raw cross would have flipped one week earlier (2026-03-16).

**Reading:**
- MU's two largest 2026 pullbacks never left the band on either z. Only `pullback_sigma` reached −2. This is why Q09.2 matters and why `pullback_sigma` is shown beside the band.
- MSTR is a 12-month loser with a sharp one-month rebound. PT and ST disagree; both are shown and the profile weights decide.

## Cases the rules must handle
1. Completed bars only: the partial current week, or a tracked name's week whose last session is not fetched yet (rotation), is excluded; the older `as_of` is shown.
2. Short history → "insufficient_history (n/N)": SPCX (first bar 2026-06-12) gets `band_z` around 2026-10-23, `rev_1m` January 2027, `trend_state` April 2027, `mom_12_1` June 2027.
3. INFQ → bars before the merger close (2026-02-13, `spac_shell`) excluded; Tiingo's stored history there is unchecked.
4. Missing days never filled. Stale bars (over 5 days) → "missing: stale bars", stale badge.
5. Dividend or split → a full refetch rewrites adjusted history; the current week is recomputed, older rows keep the basis named in `method`.
6. Earnings 8-K inside the `rev_1m` window, or the session after an after-close filing (`accepted_at`) → `news_move`, "drift expected", never a reversal candidate. Tesla's deliveries report also carries Item 2.02 (LESSONS, D-M02-23); both count as news.
7. High-turnover large caps (TSLA, NVDA, MSTR candidates) can continue rather than reverse → every `rev_1m` row says "turnover not checked (deferred)".
8. ST and PT disagree (MSTR) → both shown; weights decide (D12 profile of record).
9. Beyond 2σ: gate pass or warn and CvD CYCLICAL_TROUGH → "stronger" (D27); any other or missing CvD → warning, no added strength.
10. Gate fail, incomplete or not applicable (ETV `fund`) → "not qualified", value shown, R17 note; CvD missing until Part 8a → "qualification incomplete". MSTR: no special rule (D-M04-8). Tracked names → "qualification: not covered by M04 (D-M04-80)".
11. Repeated `below_2` weeks in a decline (MSTR November → June) → shown each week with the falling-knife label; cooldown deferred.
12. Upper extreme (`above_2`) → information only (Q09.3); never a sell signal (D16).
13. Parabolic run → `up` to the top; `ma_distance` shows the stretch. Whipsaw near the MA → 2-close rule, "pending flip" after one close.
14. Old peak as an anchor → the 52-week-high ratio is momentum context, never a target. SPY missing → "missing: SPY not stored" in `method`.
15. Fat tails → labelled "normal-model band; hit rates uncalibrated" (Cont 2001, S-new-M09-10). Trend inflates σ of price (MU) → Q09.2; `pullback_sigma` always shown.
16. Literature effects → labelled literature, not forecasts (smaller after publication; cross-sectional in origin, ours time-series). Profile shopping → decisions log the profile (D12). Tiingo values stay internal (S68).

## Deferred to the tuning phase
- R1: `mom_12_7`, `rel_mom_spy` and the 52-week-high ratio as own signals (in `method` first); turnover context on `rev_1m` and `turnover_pctile` (inputs stored, see above; pack 1.2); `news_context` from `news_item` (news only from October 2026); industry momentum (needs M02 baskets as price series); M02's L7 customer-to-supplier return lead (D-M02-7, later part).
- R2: `market_regime` and panic with SPY + FRED VIX (reuse M10's FRED client once built; M12 after the MVP); ST on daily bars (10/50-day, `rev_1w`; needs M01's ST column).
- R3: volatility panel (Yang–Zhang, ATR14, `vol_regime`; pack 3.2) and empirical band (information only); per-stock band calibration and outline TA 3's MA length (needs the backtest).
- R4: cooldown, trigger log, `m09_qualify` (no alerts in the MVP).
- R5: `range_state` (Q09.8; pack 5.2 timeframe).
- R6: state-flip digest (no alerts); walk-forward backtest, strength per signal and whether a backtest gates weight (pack 6.3), PT/ST rows for M01 (6.2); `technical_signal` table (settled by D-M04-9).
- Exit side of the outline's "determine entry/exit points": no technical exit signal in the MVP; `trend_state` `down` is context; exits stay M01 rule 4 and M11 (D16).

## Questions for the owner
Answer as "Q09.1a Q09.2a …".

**Q09.1 Which signals make the MVP?**
- **(a) Recommended:** the four above, one lead per horizon: `band_z` (MY), `trend_state` (MY context), `mom_12_1` (PT), `rev_1m` (ST). Why: A4 is binding and all four compute locally from stored prices with no new fetch (D31).
- (b) MY only (`band_z`, `trend_state`); PT and ST wait for M01's PT/ST columns.
- (c) (a) plus `market_regime` (SPY and FRED VIX, a new fetcher).

**Q09.2 What does D27's σ measure? The rule itself stays unchanged.** (M12's add-zone block, Q12.6, uses the same σ.)
- **(a) Recommended:** z of ln(close) against the 20-week mean of ln(close), with `pullback_sigma` shown beside it; the backtest picks at tuning. Why: it stays inside M01's approved "20-week mean ± σ" while showing the misses MU exposes (S-new-M09-10).
- (b) Switch the trigger to `pullback_sigma` now. This would change M01's definition (D6).
- (c) z of the price level, as M01 and the outline word it.

**Q09.3 Does the band also mark tops?** (Answer together with Q12.5, M12's "calls at tops".)
- **(a) Recommended:** signed `band_z`; `above_1` and `above_2` labelled "upper extreme — information" for M12 later. Why: outline TA 3 asks for tops (calls) and bottoms (puts); R20 (modified) keeps the call window regime-based and signal-only.
- (b) Lower side only, as in the pack.

**Q09.4 The source of R3's "qualified" is settled (M04 notes; D-M01-5, -6: `survival_gate`, `filing_status`, `cvd_state`). What covers the gap until Part 8a writes `cvd_state`?**
- **(a) Recommended:** nothing extra: the label reads "qualification incomplete" (gate and filing status shown), no new review kind. Why: 8a is the next M04 part (D31), and no strength is granted before weights exist anyway.
- (b) An interim owner flag in `config/technicals.toml` (qualified, date) until 8a.
- (c) (a) plus an `m09_qualify` review item for names M04 cannot classify (tracked names, ETV).

**Q09.5 What role does the 40-week trend play, and when does it flip?**
- **(a) Recommended:** context and warning only. The position flips after 2 consecutive weekly closes and the MA slope sets up, flat or down. A "falling-knife context" label shows when `mom_12_1` < 0 and the trend is down. It never blocks. Why: trend rules fail out of sample and after costs (Bajgrowicz & Scaillet, S-new-M09-7); warnings only (D16).
- (b) As (a), but flips on the raw cross.
- (c) Block tranche adds while the trend is down. This is a change to M01 rule 3 (D6).

**Q09.6 Add SPY now?** (The one exception to D31's "stored data"; M10's Q10.7a asks for the same symbol — one addition serves both.)
- **(a) Recommended:** yes. One Tiingo request a day (one full-history request first), within the 480 symbols a month (S68, D-UI-19). It feeds SPY's 12-1 and trend into `method` and is M01's "S&P 500 total return" proxy for M11 (R5, labelled proxy). Why: it fills two open inputs at almost no cost.
- (b) No, wait for M10 or M11.

**Q09.7 How is R17's warning worded?**
- **(a) Recommended:** use measured base rates: "decline risk: about 40% of Russell 3000 stocks since 1980 suffered a permanent fall of 70% or more from peak (57% in IT; JPM 2014); 58% trailed T-bills (Bessembinder)". Why: no measured source reaches 80% (S-new-M09-12, S01), and a shown number gets read as a forecast.
- (b) Keep "80%", labelled heuristic.
- (c) Show both.

**Q09.8 What is the "augmented trading range" (Q2)?**
- **(a) Recommended:** for the MVP, M01's σ band is the range "we create" (the outline allows "or create one"). The named range is chosen at tuning from a chart mock-up of the candidates on stored data. Why: no standard definition was found (pack Round 5; S-new-M09-7, -13).
- (b) Define it now: the 20-day high–low widened by ±1 ATR14, close-confirmed breaks.
- (c) You describe it in one sentence now.

## Build parts
**Part 1 — Technicals compute (branch `m09-part1`, Medium)**
- **Goal:** the four signals for every priced name, after each refresh.
- **Code:**
  - `src/engine/technicals/bars.py`: completed-week reader on `price_bar` (US Eastern dates). A week counts as complete when its last session matches the core-symbol calendar; shell-period cut-off. The M10 and M12 briefs can reuse it.
  - `signals.py`: the four signals. `qualify.py`: reads M04 via `signals.latest_signal`; label only.
  - `step.py`: a local pass in `scripts/run_refresh.py` after the M04 local steps (`financials_gate_local_step`, `financials_quality_local_step`), short write transactions (LESSONS).
  - `config/technicals.toml`: frozen parameters, `v1`.
  - If Q09.6a: SPY added as a benchmark symbol in `prices_step`, with no cik and no D13 rows (shared with M10).
- **Tables:** none expected (D13 `signal`); a migration number only if the build finds a need. **Review kinds:** none. **Docs:** new `docs/M09_TECHNICALS.md` (MODULE_TEMPLATE, failure modes per D9, from the pack's tables); DATA_SOURCES DS8 (SPY).
- **Live check:** `uv run python scripts/run_technicals.py signals` (`--no-fetch` skips SPY); 0 SEC, 1 Tiingo request (SPY's first fetch), under a minute; summary on screen, full log in `logs/`: one line per name (four values, zones, as_of, missing reasons) checked against the MU, MSTR and SPY figures above (Yahoo vs Tiingo may differ slightly).
- **Fixtures:** synthetic series (steady trend, crash, partial week, missing days, dividend refetch, SPCX-length history, INFQ shell cut-off); the pack's MSTR checkpoints (170.50, 82.31) as known-answer tests; earnings `event` rows; M04 `signal` rows for each gate and CvD state, including missing; a symbol without a CIK.
- **Depends on:** M04 4a (built); 8a for `cvd_state` (missing until then; this part does not wait for it).

**Part 2 — Technicals tab and chart overlays (branch `m09-part2`, Medium)**
- **Goal:** a mock-up first on scratch data (D-UI-4, port 8799), then the build.
- **UI:** a new company tab "Technicals": per profile, the four signals with value, zone or state, as_of, `method` on hover, missing reasons, the M04 reading line, and the R17 note under any `below_*` zone. Weekly chart overlays: 40-week MA and the 20-week ±1/±2σ band. The Overview signal list gains the M09 rows.
- **Live check:** you run the app on the real DB and comment; 0 requests.
- **Fixtures:** tab render tests including missing rows (no Python objects, D-UI-7).
- **Depends on:** Part 1.

## Open risks
- No backtest: the band choice (Q09.2) is unvalidated; MU shows a mean-based band can miss trend pullbacks. No rule-7 strength until Part 8a writes `cvd_state`.
- `rev_1m` without turnover can misread continuation as reversal in large caps (Medhat & Schmeling, S-new-M09-2).
- PT/ST weights are proposals until M01's PT/ST columns adopt them; S-new-M09 IDs are provisional until SOURCES.md renumbering (from S226).

## Check notes (2026-10-13)
Adversarial check against the pack, the outline, DESIGN, M01, M04 (Signals out, build-log notes), DATA_SOURCES, LESSONS, the migrations and `src/engine/`.
1. **Outline fit.** TA 4 (confluence) was named but not placed → Purpose now says core's D13 score combines it and M09 never buys alone. The outline's "determine entry/exit points" (exit side) and "don't chase the initial move" were silent → exit side added to Deferred; `ma_distance` tied to "don't chase".
2. **Binding decisions.** Q09.4 re-asked a settled point (the M04 notes and D-M01-5/-6 fix the source of `qualified`) → reframed to the open part only (what covers the gap until 8a). D-M04-74 (cik key), D-M04-35 and D-M04-80 added to the binding line. The weights line had folded in pack 6.3a (no weight before a backtest) as if decided → now "once core D13 weights exist", with 6.3 listed under Deferred.
3. **Data reality.** Names checked in code: `price_bar`, `price_fetch.cik` (0012), `STALE_AFTER_DAYS`, `bars()`, `event` (0006; `category`, `accepted_at`), `signal` (0029; cik NOT NULL), `write_signal` / `latest_signal`, `financials_gate_local_step`, `prices_step`, `company_models.toml` tags, `cover_shares` (0029). Fixes: the D13 key (`cik`) was never stated → added, with "no CIK → no rows" (SPY); turnover was listed as a data gap (META/MSTR/GOOG share series), but M04 Part 1a stores class-summed cover counts (D-M04-2) → moved to "stored but unused"; the gap list gained request costs (SPY, VIX); the step now runs after both M04 local steps; US Eastern dates (D-SEC-16) and short transactions (LESSONS) added; row-writing rule stated (no history backfill into `signal`; case 6 no longer rewrites all past rows). The Tesla Item 2.02 deliveries claim checked out (LESSONS, D-M02-23) and now cites it.
4. **Numbers and sources.** All worked-example figures trace to the pack (Rounds 1–4). Two readings were unsupported: MSTR 2026-06-26 → `down` (the MA slope is not in the pack) → marked illus.; MSTR's `rev_1m` `extended_up` (no σ_w in the pack, and no zone threshold was defined) → replaced by "depends on σ_w", and a starting threshold |z| ≥ 2 (config, unsourced, matches the band) added to the signal row. Q09.7's "never recovered" overstated JPM's "permanent decline" → reworded. `trend_state`'s 45 bars vs the pack's 44 explained. Source IDs (S01, S12, S68, S-new-M09-1…14, D-UI-19, DS5) exist.
5. **MVP discipline.** 4 signals, 8 questions, 2 parts, a sub-minute live check: fine. D13 fields now complete (cik, value vs value_text, missing rows, grade, MY/PT/ST with `info`). Part 1 now names the module doc (`M09_TECHNICALS.md`, D9 failure modes) and DATA_SOURCES, per CLAUDE.md's same-commit rule. Length trimmed (cases 22 → 16, departures, data rows, risks); the body is still about 19k characters, above the 15k target, because the D13 key, gap costs and cross-module references were added.
6. **Overlap.** M10's brief adds the same SPY symbol (Q10.7a) and a FRED client (also M12's) → Q09.6 and Deferred R2 point to one shared addition; `technicals/bars.py` offered to M10 and M12 (M12's brief expects an M09 helper). Q09.3 and Q09.2 cross-referenced to Q12.5 (calls at tops) and Q12.6 (add-zone σ) so the answers agree. M04's `overreaction_gap` (8a) is a price-vs-fundamentals gauge, not a technical signal: no overlap. No M02/M04 signal duplicates the four.
