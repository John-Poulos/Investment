# M09 — Design review pack (draft for the owner)

**Status:** research only — nothing is decided until the owner answers (D7); 2026-10-12 · **Effort:** High for this review; each build part Medium. Outputs are research signals, not financial advice.

## Purpose and dependencies
**Question M09 answers.** What does a stock's own price history say about timing at each horizon? The A4 split is: reversal for ST, momentum for PT, and entry timing for a fundamentals-led MY.

**Approved items it must honour**
- **A4:** reversal (ST), momentum (PT), fundamentals-led (MY).
- **R3:** mean reversion only on fundamentally qualified names.
- **R17:** "80% dead or dying" is a heuristic.
- **D27 and M01 rules 1, 3 and 7:**
  - 1–2σ triggers, with depth reported uncapped.
  - Beyond 2σ grades stronger only when CvD = CYCLICAL_TROUGH and the survival gate passes.
- **Engine rules:**
  - D10: every signal is visible in every profile.
  - D12: positions keep a profile of record.
  - D13: signal record; D14: evidence grades.
  - D16: warnings only; D8: ambiguous cases go to the review queue; D9: failure modes are documented.
- **R20 (M12):** the covered-call window needs "regime weak/sideways", so M09's trend and regime states feed it.
- **Q2 ("augmented trading range")** is prepared here (Round 5).

**Depends on**
- **M00:** `price_bar` (Tiingo, DS8; S68, S69); `event` (8-K Item 2.02 → category `earnings`, migration 0006); XBRL share facts.
- **M02:**
  - `news_item` / `news_company` (migration 0025; history starts October 2026);
  - the tracked-name universe (D-M02-12);
  - theme baskets, later, for industry momentum.
- **M01:** the MY parameters (40-week MA, 20-week band) and the PT/ST columns that M09 proposes (Round 6).
- **M04:** CvD state, survival gate and the shares concepts (M04 question 1.1). None of these is built yet.
- **Consumers:**
  - M01 (entry plan);
  - M11 (sizing information, R23);
  - M12 (regime);
  - M10, which overlaps on market regime.

**Data note.**
- Claude cannot read `data\`. Every real price figure comes from the Yahoo Finance chart API (grade other, S-new-M09-14), read on 2026-10-12.
- Figures use weekly adjusted closes with Monday-keyed weeks; the last row is the week that closed on Friday 2026-10-09.
- A second check reproduced every figure. All of them get recomputed from `price_bar` at build.
- Most papers were checked against abstracts or listings (RePEc, NBER, SSRN mirrors, publishers), not the full text.

**How to answer.**
- Plain text, e.g. "1.1a 1.2a 1.3a".
- Suggestions stand or fall with your answers. Strike any by number ("S2.3 no") or reply "rest ok".
- Answers become D-M09-1 onward.
- Every threshold here is a starting value, frozen in config before the backtest (Round 6).

---

## Round 1 — What price history predicts at each horizon (A4)

### What the research says
1. **One week to one month: reversal.**
   - Last week's winners and losers reverse the next week, net of spreads and plausible costs (Lehmann 1990, S-new-M09-1).
   - Monthly returns are forecastable one step ahead (Jegadeesh 1990, S12).
   - French's short-term reversal factor uses the prior month, "1-1" (S-new-M09-5).
2. **Reversal is not universal.**
   - Double-sorted on turnover, low-turnover stocks reverse and high-turnover stocks continue ("short-term momentum"). Continuation is strongest in the largest, most liquid and most covered stocks (Medhat & Schmeling 2022, S-new-M09-2).
   - Their turnover sort is market-wide. Which watchlist names count as high turnover is unknown until we compute it; TSLA, NVDA and MSTR are candidates.
3. **The part that reverses is the move with no news.** Both findings are S-new-M09-3.
   - The part of a return not explained by cash-flow news (analyst revisions) reverses. A strategy built on it earns about 4× the risk-adjusted return of standard reversal (Da, Liu & Schaumburg 2014).
   - Extreme moves without news reverse; moves with news drift, most after bad news, mainly in smaller and less liquid stocks (Chan 2003).
4. **Three to twelve months: momentum.**
   - Past winners minus past losers earn significant returns over 3–12-month holds, and part of that dissipates over the next two years (Jegadeesh & Titman 1993, S12).
   - French's momentum factor uses months 2–12, skipping the latest month (S-new-M09-5).
   - Months 12–7 drive most of the effect, and recent-past strategies are weaker among the largest, most liquid stocks (Novy-Marx 2012, S-new-M09-4).
   - Profits show no reliable relation with size, and about half come from the long side (Israel & Moskowitz 2013, S-new-M09-4). This matters for a long-only, large-cap list.
5. **Nearness to the 52-week high.**
   - It dominates and improves on past returns, and its forecasts do not reverse in the long run (George & Hwang 2004, S-new-M09-4).
   - Du (2008), cited secondhand, reports momentum and reversal co-existing in international indexes.
6. **Industry momentum** explains much of stock momentum (Moskowitz & Grinblatt 1999, S-new-M09-4). This is a natural link to M02 theme baskets.
7. **Three to five years: long-term reversal.**
   - 36-month losers beat winners by about 25% over the next 3 years, much of it in January (De Bondt & Thaler 1985, S12). The figure comes from a secondary page that now returns 403.
   - Critiques point to low prices and bid-ask bounce (Conrad & Kaul 1993; Ball, Kothari & Shanken 1995; secondhand, S-new-M09-1).
   - French's long-term reversal factor uses months 13–60 (S-new-M09-5).
   - Inference: long-horizon losers mix overreaction with genuine decline, which supports A4's fundamentals-led MY.
8. **Earnings drift.**
   - The top-minus-bottom earnings-surprise deciles were positive in 41 of 48 quarters in 1974–85 (Bernard & Thomas 1989, figures via a secondary source, S-new-M09-6).
   - An earnings gap is news, so continuation is expected, not reversal.
9. **Decay after publication.** Across 97 predictors, returns are 26% lower out of sample and 58% lower after publication (McLean & Pontiff 2016, S-new-M09-6).

**Data.**
- `price_bar` stores raw and adjusted OHLCV plus dividend and split factor (migration 0012).
- `bars()` in `prices/store.py` returns Monday-keyed weekly bars **including the partial current week**.
- Turnover = volume ÷ shares outstanding, from XBRL. Per the M04 pack:
  - META and MSTR have no non-dimensional share count;
  - GOOG has no dei cover count.
  These stay missing.
- Analyst revisions are not free.
- Tracked names are chosen by theme (soft cap about 150, 3-day rotation, D-M02-12), so ranks inside our universe would be biased.

### Worked example — MU, MSTR, SPY (Yahoo weekly adjusted, other)
| | MU | MSTR | SPY |
|---|---|---|---|
| 12-1 momentum (week of 2025-10-06 → week of 2026-09-07) | 181.42 → 975.26 = **+437.6%** | 304.79 → 130.97 = **−57.0%** | 646.05 → 762.40 = +18.0% |
| Last 4 weeks (to week of 2026-10-05) | +5.5% | **+17.8%** | +2.1% |
| Last close ÷ 52-week intraday high (Yahoo meta) | 1029.00 / 1255.00 = 82.0% | 154.34 / 315.95 = 48.8% | 778.57 / 781.62 = 99.6% |

How to read it:
- **MU** is a PT momentum leader.
- **MSTR** is a 12-month loser with a sharp one-month rebound. ST and PT point in opposite directions, which is why both are shown and weighted by profile.
- Measured against its highest *weekly* close (1133.82), MU reads 90.8% instead of 82.0%, so the definition matters (case 9).

### All cases
1. Full history → all values, computed on completed bars.
2. Partial current week → excluded; `as_of` = last completed week.
3. A tracked name whose week has ended but whose last session is not yet fetched (3-day rotation) → that week is incomplete; `as_of` stays on the prior week.
4. Fewer than 53 weekly bars → `mom_12_1` NULL, reason `insufficient_history (n/53)`. SPCX stays NULL until about June 2027; INFQ needs checking.
5. Missing days → never filled; the window is flagged.
6. Dividend or split → a full refetch rewrites adjusted history → recompute.
7. A move on an 8-K Item 2.02 day → `news_context = earnings`, labelled "drift expected"; never a reversal candidate.
8. A move on another 8-K day or a news-item day → `news_context = news`. News history starts only in October 2026, so backtests use 8-Ks only.
9. "52-week high" has three possible bases, which give different ratios: daily adjusted close (the definition), intraday high, weekly close.
10. Turnover high against the stock's own history → continuation more likely; no reversal strength.
11. No share count (META, MSTR, GOOG cover; ETV to check) → `turnover_pctile` NULL, reason `missing_shares`.
12. A split between the volume date and the share date → use raw volume with same-date shares, or split-adjust both sides. Never `adj_volume` with as-reported shares.
13. SPY not stored → `rel_mom_spy` NULL.
14. ST and PT disagree (MSTR) → both shown; profile weights decide.
15. Closed-end fund (ETV) → price signals as usual; turnover source to check.
16. Symbol delisted or renamed → bars stop; `stale`.

### Suggestions
- **S1.1** Compute every signal in every profile (D10); only the weights differ.
  - **ST** leads with `rev_1w` and `rev_1m`, z-scored by the stock's own volatility, each with turnover and news context.
  - **PT** leads with `mom_12_1`, plus `mom_12_7` and `hi52_ratio` (close ÷ highest daily adjusted close over 252 sessions).
  - **MY** has no leading price signal. Technicals time the entry (M01), and long-term reversal is context only.
- **S1.2** Use time-series and benchmark-relative measures rather than ranks inside a 16-name or theme-biased universe:
  - the sign of `mom_12_1`;
  - `rel_mom_spy`;
  - a percentile against the stock's own 10-year history.

  The literature is cross-sectional, so these versions must earn their weight in our own backtest.
- **S1.3** Add an `earnings_gap` marker from `event` rows with category `earnings`. Moves on those days are labelled "news: drift expected".
- **S1.4** Compute everything on adjusted closes of completed bars, locally, after the price step. No new API calls.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| 12-1 momentum | Crashes when a falling market rebounds and losers spike (Round 2) | Market-state flag; warning, never a block |
| 1-week / 1-month reversal | Becomes continuation in high-turnover large caps | Turnover context; no reversal strength when turnover is high |
| Turnover tercile | No market-wide universe to rank against | Own-history percentile, labelled "approximate" |
| Any price move | An earnings or news move treated as noise | Tag 8-K Item 2.02 and news-item days as `news` |
| Literature effects | Smaller after publication; watchlist chosen by the owner (survivorship) | Backtest on own history; effect sizes labelled as literature, not forecasts |
| Weekly bars | Partial current week used as a closed bar | Completed bars only; `as_of` = last completed week |
| Short history | Windows filled or zeroed | `value = NULL`, `insufficient_history (n/N)` |

### Questions
**1.1 What leads PT momentum?**
- (a) *Recommended.* 12-1 time-series momentum plus 52-week-high nearness, both shown. Why: 52-week nearness improves on past returns and does not reverse long run (George & Hwang).
- (b) 12-1 only.
- (c) 6-1, matching Jegadeesh & Titman's 6/6 strategy.

**1.2 How should ST reversal work on high-turnover names?**
- (a) *Recommended.* Show the value, label it "high turnover: continuation more likely", and give it no reversal strength. Why: large, liquid, high-turnover stocks continue rather than reverse (Medhat & Schmeling).
- (b) Treat all names the same.
- (c) Drop ST reversal until the ST profile is designed.

**1.3 What should momentum be compared against?**
- (a) *Recommended.* Own history and SPY only. Why: ranks inside a 16-name, theme-chosen list are biased.
- (b) A rank within watchlist plus tracked names.
- (c) A broad universe later (more Tiingo symbols or paid data).

---

## Round 2 — Trend and market-regime filters (M01's 40-week MA, market state, momentum crashes)

### What the research says
1. **Moving-average and trading-range-break rules.** On the Dow 1897–1986, returns after buy signals were higher and less volatile than after sell signals (Brock, Lakonishok & LeBaron 1992, S-new-M09-7).
2. **Data snooping.** Both studies are S-new-M09-7.
   - Sullivan, Timmermann & White (1999) tested 7,846 rules under White's Reality Check. Brock, Lakonishok & LeBaron's results survive in sample, but the best rule fails in 1987–96. The count and years come from the paper; the FMG page shows only the abstract.
   - On the Dow 1897–2011, the future best rules could not have been picked in advance, and even in sample low costs offset the performance (Bajgrowicz & Scaillet 2012).
   - Conclusion: a trend rule is context and risk information, not an edge on its own.
3. **Time-series momentum.** All S-new-M09-8.
   - Returns persist for 1–12 months and partly reverse later, across 58 liquid futures and forwards (Moskowitz, Ooi & Pedersen 2012). The evidence covers diversified futures, not single stocks.
   - Kim, Tse & Wald attribute much of the alpha to volatility scaling (secondhand).
   - Hurst, Ooi & Pedersen (2017) extend trend-following evidence back to 1880 (other). Their drawdown statistics are not verified and are not used.
4. **Faber's 10-month SMA** (2007) is close to M01's 40-week MA. Other; unverified (SSRN returned 403).
5. **Market state.** Both S-new-M09-9.
   - Momentum earned 0.93% a month after up markets and −0.37% after down markets, 1929–95 (Cooper, Gutierrez & Hameed 2004).
   - A UK study did not find this pattern (Galariotis et al. 2014).
6. **Momentum crashes** happen in "panic" states after declines with high volatility, and they coincide with market rebounds. Past-loser betas exceed 3 after major declines (Daniel & Moskowitz 2016, S-new-M09-9).

**Data.**
- **SPY is not stored.** Adding it costs one Tiingo request a day, within the 480-symbol monthly cap (S68, D-UI-8/19).
  - It would also fill M01's "S&P 500 total return" proxy input: adjusted close, labelled as a proxy.
- **VIX:** FRED `VIXCLS` (15.41 on 2026-10-08) is Cboe data reprinted with permission, so it is for internal use (S-new-M09-14).
  - No FRED fetcher exists yet. The API needs a free key; the fredgraph CSV endpoint may not. Verify at build.
- **Sector ETFs** (e.g. SMH) are optional, at one symbol each.

### Worked example — SPY (Yahoo weekly, other)
| Week of | Close | 40-week MA | vs MA | MA 4-week slope | Reading |
|---|---|---|---|---|---|
| 2026-10-05 | 778.57 | 721.29 | +7.9% | +1.3% | Up. 24- and 36-month returns are positive, so Cooper et al.'s "up" state applies and momentum gets normal weight |
| 2026-03-23 | 630.89 | 656.64 | −3.9% | +1.0% | Below the MA, 8.4% below the 688.69 peak to date. Not a bear market: the 24-month return was positive |

In the week of 2026-03-23, MU fell 15.5% (422.66 → 357.02) and MSTR closed at 126.03.

Flip timing for SPY:

| Rule | Flips down | Flips up |
|---|---|---|
| Raw cross | week of 2026-03-16 | week of 2026-04-06 |
| 2 consecutive closes | week of 2026-03-23 | week of 2026-04-13 |

This was a real three-week dip, not whipsaw. It shows the one-week delay that hysteresis costs, not a whipsaw it saved; the benefit has to be measured in the backtest.

### All cases
1. Above a rising MA → `up`.
2. Below a falling MA → `down`.
3. Above a falling MA, or below a rising one → `flat` (proposal).
4. One close across the MA → "pending flip" shown; state unchanged.
5. Second consecutive close across → flip.
6. Fewer than 44 weekly bars (40 for the MA + 4 for the slope) → NULL, `insufficient_history`.
7. Parabolic run → reads "up" right to the top; `ma_distance` shows how stretched the price is.
8. ST profile with fewer than 50 daily bars → NULL.
9. Market regime takes one of these states:
   - `up`;
   - `below_ma` but not bear (March 2026);
   - `bear` (24-month return < 0);
   - `panic` (24-month return < 0 and VIX in its top tercile);
   - a rebound out of panic → momentum-crash warning.
10. VIX missing (FRED unreachable) → regime from SPY alone, labelled "partial".
11. SPY not stored → `market_regime` NULL.
12. FRED and Tiingo dates differ (holidays, publication lag) → align on the last common date.
13. Profile switch → same state, different weight (D12).

### Suggestions
- **S2.1** `trend_state` per profile, needing 2 consecutive closes to flip:
  - **MY:** close vs 40-week MA plus the MA's 4-week slope → up, down or flat;
  - **PT:** sign of 12-1 momentum with the 40-week state;
  - **ST:** 10-day vs 50-day average, fixed before backtesting.
- **S2.2** `market_regime` from three inputs:
  - SPY vs its 40-week MA;
  - the sign of SPY's 24-month return;
  - VIX's percentile against its own history.

  "Panic" = 24-month return below zero and VIX in its top tercile. Daniel and Moskowitz's exact bear-market window is to be rechecked in the full text. `panic` lowers the PT momentum weight and never blocks (D16).
- **S2.3** In MY the trend is context for M01 rule 1, never a block:
  - downtrend and qualified → label "early";
  - downtrend and not qualified → warning.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Price vs 40-week MA | Whipsaw near the MA; lags at turns; reads "up" to the top of a parabolic move | 2-close hysteresis; MA slope and distance shown |
| Regime from one index | One index stands in for the whole market | SPY plus VIX shown; labelled proxy |
| Many rules tried | Best rule picked after the fact | Parameters frozen in config before any backtest; version in `method` (D13) |
| "Panic" state | Momentum crashes while losers rebound | `panic` warning lowers PT momentum weight; never blocks (D16) |

### Questions
**2.1 What role does the 40-week filter play in MY?**
- (a) *Recommended.* Context and warning only. Why: trend rules fail out of sample and after costs (Bajgrowicz & Scaillet), and D16 keeps exits as warnings.
- (b) Block tranche adds while price is below a falling 40-week MA.
- (c) Wait until the MA is reclaimed.

**2.2 Where does the market regime come from?**
- (a) *Recommended.* SPY via Tiingo plus FRED VIX. Why: the momentum-crash state needs both a past-return input and a volatility input (Daniel & Moskowitz).
- (b) SPY only.
- (c) None until M10.

**2.3 When does `trend_state` flip?**
- (a) *Recommended.* After 2 consecutive weekly closes past the MA. Why: simple, fixed in advance; the backtest measures its one-week cost.
- (b) A ±x% band.
- (c) On the raw cross.

---

## Round 3 — Volatility, and what the σ in M01's bands measures (D27)

### What the research says
1. **Stylized facts.** Returns have heavy tails, and volatility clusters and varies over time (Cont 2001, S-new-M09-10). Normal-model σ bands misstate hit frequency, as M01's failure-mode table already notes.
2. **Range estimators.** Both S-new-M09-10.
   - Parkinson (1980) uses the high–low range and ignores overnight gaps.
   - Yang & Zhang (2000) is drift-independent, handles opening jumps, and has the smallest variance among estimators with similar properties.
3. **ATR (Wilder 1978).** True range includes gaps, and ATR is a Wilder-smoothed average, usually over 14 periods. It measures volatility, not direction (other, S-new-M09-10).
4. **Volatility scaling.** All S-new-M09-11.
   - Managing momentum's risk virtually eliminates crashes and nearly doubles its Sharpe ratio (Barroso & Santa-Clara 2015).
   - Volatility-managed factors show higher Sharpe ratios and alphas (Moreira & Muir 2017).
   - Single-factor management fails out of sample (Cederburg et al.) and after costs (Barroso & Detzel), both as cited by DeMiguel, Martín-Utrera & Uppal (2024). Their conditional multifactor version still outperforms out of sample, net of costs.
5. **Idiosyncratic volatility.** High idiosyncratic volatility goes with very low average returns (Ang, Hodrick, Xing & Zhang 2006, S-new-M09-11). A volatility spike alone does not make a stock cheap.
6. **M01's band is a Bollinger band.** "20-week mean ± kσ" is a Bollinger band on weekly closes; %b and BandWidth are its standard read-outs (other, S-new-M09-10).
7. **Computed here:** in a strong trend, the 20-week σ of price *levels* is driven by the trend itself, so the band can miss real pullbacks (MU below).

**Data.**
- Adjusted OHLC is stored, so close-to-close, ATR, Parkinson and Yang–Zhang all compute locally; missing days are skipped.
- No intraday data. Implied volatility is not free (Q5, M12).
- Idiosyncratic volatility needs SPY, and is then a market-model residual, not Ang et al.'s three-factor residual.

### Worked example — TSLA daily, MU weekly (Yahoo, other)
TSLA, daily bars from 2026-08-07 to 2026-10-09:

| Measure | Value |
|---|---|
| ATR14 (Wilder) | 11.73 = 3.07% of the 382.70 close |
| 20-day vol, close-to-close (annualized) | 30.4% |
| 20-day vol, Parkinson | 27.0% (lowest: ignores overnight gaps) |
| 20-day vol, Yang–Zhang | 33.9% (weights the overnight, open-to-close and range parts separately) |
| Largest daily move | 2026-09-04, −5.92% ≈ 3.2× the latest 20-day daily σ (a window that excludes that day) |

With 20 observations, the differences between estimators are within sampling noise.

MU's σ_w over 20 weeks is 10.4% a week (75.1% annualized), against SPY's 1.5% (10.8%).

| MU pullback | Close | 20-week high | Depth | z of price (M01 as written) | z of log price | `pullback_sigma` |
|---|---|---|---|---|---|---|
| Week of 2026-03-23 | 357.02 | 427.92 | −16.6% | +0.24 | +0.32 | **−2.01** |
| Week of 2026-07-27 | 823.03 | 1133.82 | −27.4% | +0.30 | +0.43 | **−2.43** |

M01's price-level band fired on neither of MU's two largest pullbacks of the year. A pullback measured in return σ would have fired near −2σ both times. That is two cases from one stock; the backtest decides.

### All cases
1. Normal stock → `band_z`, `pullback_sigma` and the volatility panel are all computed.
2. Strong uptrend → σ of levels is inflated; the band misses pullbacks (MU).
3. Crash → σ of levels lags; the band fires late.
4. Earnings gap inside the 20-day window → volatility shown with and without earnings days.
5. Missing days → estimators skip them; too few observations → NULL.
6. Bad split adjustment → a true range over 5× ATR is flagged for checking, not used.
7. Halt or zero-range day (high = low) → flagged; adds nothing to Parkinson.
8. Annualization → 252 for daily, 52 for weekly; bar size stored with every value.
9. Fewer than 20 weeks → band NULL. Less than 3 years → `vol_regime` NULL (SPCX).
10. Very volatile names (MSTR) → `vol_regime` judged against the stock's own history.
11. SPY missing → idiosyncratic volatility NULL.
12. Fat tails → band hits exceed the normal-model rate; an empirical band is shown alongside.

### Suggestions
- **S3.1** Define M01's σ explicitly and show two depths:
  - `band_z` = z of ln(close) against the 20-week mean of ln(close);
  - `pullback_sigma` = ln(close ÷ 20-week high) ÷ σ_w, where σ_w is the standard deviation of weekly log returns over 20 weeks.

  D27's rule is unchanged: 1–2σ triggers, uncapped depth, beyond 2σ only under the gates. Only the measurement is chosen, by backtest.
- **S3.2** Volatility panel:
  - 20-day Yang–Zhang, annualized;
  - daily ATR14 and 10-week ATR;
  - `vol_regime` (low, normal or high) from the percentile of 52-week realized volatility within the stock's own 3-year history.
- **S3.3** Calibrate bands per stock. Over the full history, count −1, −2 and −3σ hits and record the distribution of the following 26- and 52-week returns. Later, split these by M04's CvD state.
- **S3.4** Volatility scaling goes to M11 (R23) as information only, given the mixed out-of-sample evidence. M09 does no sizing.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| σ of price level | Inflated by the trend; misses pullbacks in uptrends, fires late in crashes | σ on log price or returns (S3.1) |
| 20-day σ | One earnings gap dominates the window | Shown with and without earnings days |
| Range estimators | Discrete trading and halts bias them; a bad split adjustment looks like a huge true range | True range over 5× ATR flagged, not used |
| Annualization | 52 and 252 periods mixed up | Bar size stored with each value |

### Questions
**3.1 What should D27's σ measure?**
- (a) *Recommended.* Keep the trigger on `band_z` of log price, show `pullback_sigma` beside it, and backtest both before choosing. Why: the MU cases show σ of levels misses pullbacks in trends; the backtest picks between the other two.
- (b) Switch the trigger to `pullback_sigma` now.
- (c) Keep σ of price levels.

**3.2 Which daily volatility estimator?**
- (a) *Recommended.* Yang–Zhang plus ATR14. Why: both include gaps, and Yang–Zhang has the lowest variance among comparable estimators.
- (b) Close-to-close only.
- (c) Parkinson.

**3.3 How do we guard against fat tails?**
- (a) *Recommended.* Show an empirical percentile band from the stock's own history beside the σ band. Why: heavy tails make normal bands misstate hit rates (Cont).
- (b) The σ band only.

---

## Round 4 — Mean reversion only on qualified names (R3), the R17 base rate, M01 triggers

### What the research says
1. **Measured base rates** (J.P. Morgan 2014, Russell 3000 since 1980, primary PDF read, bank research = other, S-new-M09-12):
   - About 40% of stocks suffered a permanent decline of 70% or more from peak (p. 3).
     - "Catastrophic" means a 70% fall after which the loss from peak stays at 60% or more (p. 6).
     - By sector: IT 57%, telecom 51% (p. 6).
   - About two-thirds underperformed the index, 40% had negative absolute returns, and the median excess lifetime return was −54% (pp. 3, 8).
   - 71% of IT stocks had negative excess returns (p. 9).
   - S01: 58% of stocks trailed T-bills.
   - Neither source reaches "80%", so R17 rightly stays a heuristic.
2. **Reversal applies to non-fundamental moves** (Round 1 item 3, S-new-M09-3). This supports R3: qualify the fundamentals first, then treat a technical overshoot as an opportunity.
3. **Losers keep losing over 3–12 months** (S12).
   - Inference: a 12-month loser below −2σ is still in negative momentum on average.
   - Exception: a rebound after a panic state, when losers jump briefly (Daniel & Moskowitz, S-new-M09-9).
4. **Existing gates.**
   - M01 rule 3 gates tranche adds on CvD = CYCLICAL_TROUGH, a survival-gate pass and the 1–2σ trigger.
   - Rule 7 (D27) gives depth beyond 2σ extra strength only under those gates.
   - M09 supplies the trigger and depth. M04 supplies the gates; its pack is in progress and not built.

**Data.**
- CvD and the survival gate do not exist yet, so `qualified` is missing.
- MSTR (bitcoin treasury company), ETV (closed-end fund) and SPCX (short history) may not fit CvD at all. These go to the review queue (D8).

### Worked example — MSTR weekly (Yahoo, other)
- **Week of 2025-11-17, close 170.50:** z of price −2.24 (beyond 2σ). The price then fell a further **51.7%**, to 82.31 in the week of 2026-06-22.
- **Week of 2026-06-22, close 82.31:**
  - z of price −2.22, z of log price −2.66, `pullback_sigma` −6.83;
  - 53.2% below its 40-week MA of 175.85.

  It then rose **+87.5%**, to 154.34 by the week of 2026-10-05.

Both triggers were beyond 2σ. D27 grades them stronger only under CvD and survival gates, which M04 has not defined for a bitcoin holding company. This is exactly the review-queue case.

| as_of | signal | value | qualified (illustrative) | strength (illustrative) |
|---|---|---|---|---|
| 2025-11-21 | band_z | −2.24 | unknown → `m09_qualify` | 0, warning |
| 2026-06-26 | band_z | −2.22 | unknown → `m09_qualify` | 0, warning |

### All cases
1. Qualified, 1–2σ → add trigger per M01 rule 3; M09 supplies the trigger.
2. Qualified, beyond 2σ, CvD = CYCLICAL_TROUGH and survival pass → stronger (D27).
3. Qualified but CvD is not CYCLICAL_TROUGH → depth shown as a warning, no added strength.
4. Not qualified → value shown with zero strength and the base-rate warning.
5. Qualification unknown (M04 not built, no owner flag) → `m09_qualify` review item.
6. CvD does not apply (MSTR, ETV) → review queue (D8).
7. Short history (SPCX) → no band; review item.
8. Qualification older than the latest 10-Q or 8-K → as-of date shown; recheck.
9. Repeated triggers in a decline → cooldown (S4.2).
10. 12-1 momentum negative and price below a falling 40-week MA → "falling-knife context" label.
11. Rebound after a panic state → loser-jump note (Round 2).
12. Trigger on an earnings-day drop → labelled "news: drift expected"; bad-news drift (Chan).
13. The old peak used as a target ("it was 300") → the 52-week ratio is shown as momentum only, never as a target.

### Suggestions
- **S4.1** Reversal and band signals carry `qualified` (from M04: R3 screen + CvD + survival gate) and its as-of date. If unqualified:
  - the value is shown with zero strength;
  - it carries the warning "decline risk; base rate ~40% catastrophic, 57% in IT (JPM 2014)".
- **S4.2** Cooldown on triggers: after a −2σ trigger, the next one needs a further drop of at least 1σ_w, or 8 weeks to pass (to be calibrated). Every trigger is written to a trigger log for the backtest.
- **S4.3** A "falling-knife context" label when 12-1 momentum is negative and price is below a falling 40-week MA. Warning only (D16).
- **S4.4** A new review item `m09_qualify` for names where CvD does not apply or history is too short.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Band trigger in a decline | Fires week after week (falling knife) | Cooldown; falling-knife label; CvD gate (M01 rule 3) |
| `qualified` | Quarterly fundamentals go stale against daily prices | As-of date shown; recheck after each 10-Q/8-K |
| 52-week high | Old peak becomes an anchor | Shown as momentum, never as a target |
| Base-rate note | Read as a forecast for one stock | Labelled as a population base rate, with sources |

### Questions
**4.1 What qualifies a name under R3 before M04 ships?**
- (a) *Recommended.* An owner flag per company in config (e.g. `qualified = true` plus a date). Why: R3 can be honoured now, and the review queue catches the names CvD cannot classify.
- (b) No reversal strength until M04 exists.
- (c) Partial M04 outputs as each part ships.

**4.2 How should R17 be worded?**
- (a) *Recommended.* Replace "80%" with the measured base rates and their sources. Why: no measured source reaches 80% (JPM 2014, S01).
- (b) Keep "80%", labelled as a heuristic.
- (c) Show both.

**4.3 How are repeat triggers in a decline handled?**
- (a) *Recommended.* A cooldown: a further 1σ_w drop or 8 weeks. Why: it stops weekly re-firing (MSTR fell another 51.7% after its first trigger) while still logging deeper levels.
- (b) Every week below the band.
- (c) Once per drawdown.

---

## Round 5 — Q2: "augmented trading range" (prepared question)

### What the research says
1. No standard definition of the phrase was found (search on 2026-10-12).
2. Candidate meanings:
   - **(a) Trading-range break:** buy on a break above a recent high, sell on a break below a recent low (Brock, Lakonishok & LeBaron 1992). Later tests show the best rules fail out of sample and after costs (S-new-M09-7).
   - **(b) Support and resistance:** levels published by six firms helped predict intraday trend interruptions in FX, with power varying by firm and currency (Osler 2000, Fed research, primary, S-new-M09-13).
   - **(c) Chart patterns found by kernel regression:** they add some incremental information in US stocks 1962–96 (Lo, Mamaysky & Wang 2000, S-new-M09-13).
   - **(d) Volatility-widened channels** (ATR, Bollinger, Keltner). Other.
   - **(e) Position in the 52-week range** (George & Hwang 2004, S-new-M09-4).
3. Practitioner guidance: decide first whether the market is trending before using a range method (Fidelity, other, S-new-M09-13).

**Data.** All candidates compute from `price_bar`; no new data is needed.

### Worked example — TSLA daily (Yahoo, other; channel width illustrative)
- **The range:** 20 sessions from 2026-09-14 to 2026-10-09, with a high of 388.56 (2026-10-09) and a low of 345.88 (2026-09-30). The prior 20-day high, through 2026-10-08, was 386.83.
- **On 2026-10-09** the intraday high (388.56) broke that level, but the close (382.70) did not.

| Definition | Reading on 2026-10-09 |
|---|---|
| Close-based range break | No break |
| Intraday range break | Break |
| Range ± 1 ATR14 (±11.73): 334.15 to 400.29 | Inside the range |

The same day reads three ways depending on the definition.

### All cases
1. Range-bound, inside the channel.
2. Intraday break without a close break.
3. Close break, then a failed follow-through (false breakout).
4. Gap through the range on earnings → news, not a technical break.
5. Trending market → range signals are context only.
6. Fewer than N sessions → NULL.
7. Levels must use bars before `as_of` only (no hindsight).

### Suggestions
- **S5.1** Build nothing for range signals until you answer.
- **S5.2** Show the candidates as chart overlays on real stored data (a D-UI-4 mock-up) and ask the question with that mock-up.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Range levels | Drawn after the fact (hindsight) | Levels from bars before `as_of` only |
| Breakout | False breakouts | Close-based confirmation; follow-through logged |
| Support and resistance | Self-referential levels | Labelled as context |
| Many definitions tried | Data snooping | One definition fixed before the backtest |

### Questions
**5.1 "What does 'augmented trading range' mean in your outline? Please quote the sentence."**
- (a) *Recommended as a starting guess* (no standard usage was found): the recent high–low range widened by a volatility allowance (e.g. ±1 ATR), separating range-bound from breakout states. Why: it combines the range-break literature with a volatility measure M09 already computes.
- (b) Brock, Lakonishok & LeBaron's trading-range break: a close above or below the N-day high or low.
- (c) M01's σ band around a moving average, "augmented" by the fundamental gate (R3).
- (d) Position within the 52-week range.
- (e) Something else.

**5.2 Which timeframe or timeframes is it for, and is it an entry tool, an exit warning, or both?**
- (a) *Recommended.* PT and ST entry timing, shown in MY too. Why: range methods are short-horizon tools, and D10 keeps them visible everywhere.
- (b) MY entries.
- (c) Exits only.

---

## Round 6 — Output, profiles, validation and plumbing

### What the research says
1. **Output shape.** Records follow D13 with `module_id = M09`. Daily prices are grade A in M01's inputs table, and the Tiingo fields are listed in S69. Every signal is visible in every profile (D10).
2. **The D13 `signal` table already exists** (`store/migrations/engine/0001_initial.sql`).
   - `timeframe` must be MY, PT or ST, so there is no "all".
   - `evidence_grade` is required (A/B/C).
   - `value` is numeric and nullable, and there is no reason column.
   - M04 plans to be its first writer (M04 pack S1.5).
   - So text states and NULL reasons need a companion table.
3. **Fix parameters in advance.** Data snooping and post-publication decay argue for it (S-new-M09-6, S-new-M09-7).
4. **Alert fatigue** argues for putting only state changes in the digest (S86).
5. **Licence:** Tiingo data is internal use only (S68).
6. **PT/ST parameters:** M01 defines only the MY column, so M09 must propose the technical PT/ST rows.

**Plumbing.**
- SPY (and optionally SMH) at one request a day each, within the 480-symbol cap (D-UI-8/19); a FRED VIXCLS fetch.
- All computation is local, after the price step in `run_refresh.py`, in short transactions (LESSONS, D-M02-12).
- `bars()` returns the partial week, so M09 needs its own completed-bar reader.
- A full refetch after a dividend or split rewrites adjusted history.

### Worked example (values real from Yahoo; rows illustrative)
| ticker | signal | value | timeframe | grade | source_ref | method | as_of |
|---|---|---|---|---|---|---|---|
| MU | mom_12_1 | 4.376 | PT | A | price_bar adj_close 2025-10-06…2026-09-07 | mom_12_1 v1 | 2026-10-09 |
| MU | hi52_ratio | 0.908* | PT | A | price_bar | hi52 v1 | 2026-10-09 |
| SPY | market_regime | +1 = up (+7.9% vs 40-week MA) | MY, PT, ST (one row each) | A | price_bar; FRED VIXCLS | regime v1 | 2026-10-09 |
| SPCX | mom_12_1 | NULL — `insufficient_history` (18 of 53 weekly bars; first bar 2026-06-12) | PT | A | price_bar | mom_12_1 v1 | 2026-10-09 |

\*0.908 uses the highest *weekly* close (1133.82). The defined measure uses the highest daily adjusted close, so it is recomputed at build.

### All cases
1. Value present → one D13 row per timeframe.
2. Value NULL → D13 row with NULL value; the reason goes in the detail table; grade A still applies (source is `price_bar`).
3. Text state (up, flat, down, panic) → numeric code in `signal`; label in the detail table.
4. Stale bars → `Bars.stale` copied into each signal; stale badge shown.
5. Full refetch → history recomputed; `method` and `as_of` kept.
6. Config change → new `method` version; old rows kept.
7. State unchanged → no digest item. State flip → one digest item, under the weekly cap.
8. Backtest not run yet → value shown, strength 0 (under 6.3a).
9. Profile switch → same values, different weights; decisions log the profile (D12).
10. Tracked name off its rotation day → older `as_of` shown.
11. SPY or VIX missing → dependent signals NULL with a reason.
12. Sharing → values stay internal (S68).

### Suggestions
- **S6.1** A detail table `technical_signal`, keyed on (symbol, as_of, signal, profile), with `reason`, state label, bar size and `stale`. The latest value per profile also goes to D13 `signal` (question 6.4).
- **S6.2** Default weights:
  - **MY:** band and pullback depth lead (timing); trend and volatility are context.
  - **PT:** momentum, 52-week high and trend lead.
  - **ST:** reversal leads, with news and turnover context.
- **S6.3** Proposed technical rows for M01's PT and ST columns:

  | Parameter | MY | PT | ST |
  |---|---|---|---|
  | Bars | Weekly | Weekly | Daily |
  | Trend | Close vs 40-week MA + 4-week slope, 2-close flip | 12-1 sign + 40-week state | 10-day vs 50-day average |
  | Leading technicals | `band_z` / `pullback_sigma` (timing) | `mom_12_1`, `mom_12_7`, `hi52_ratio` | `rev_1w`, `rev_1m` (no news, normal turnover) |
  | Context | Trend, volatility, regime, falling-knife label | Regime (`panic` lowers weight), volatility | News, turnover, earnings gap |

- **S6.4** Parameters are frozen in `config/technicals.toml` before any backtest. A walk-forward harness on the stored watchlist and tracked history reports hit rates and forward-return distributions per signal.
- **S6.5** Technicals tab:
  - chart overlays: 40-week MA, σ band, ATR channel;
  - a state table per profile;
  - the digest carries state flips only (trend change, band trigger, earnings gap).

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Profile switching | Owner switches timeframes until a signal appears | Decisions log the profile; profile of record (D12) |
| Stale bars | Signals computed on old prices | `stale` copied into each signal |
| Adjusted-price recompute | Old values change after a dividend or split | Recompute after full refetch; `method` and `as_of` kept |
| Digest | Too many alerts | State changes only; weekly cap |

### Questions
**6.1 Which benchmark symbols?**
- (a) *Recommended.* SPY via Tiingo, also serving as M01's total-return proxy (labelled proxy). Why: one request a day fills two open inputs.
- (b) None until M10.
- (c) SPY plus sector ETFs (e.g. SMH) now.

**6.2 Who sets the PT/ST technical parameters?**
- (a) *Recommended.* M09 proposes them now (S6.3), and they are approved into M01. Why: M01's PT/ST columns are otherwise empty.
- (b) MY only for now.

**6.3 What strength do signals carry before the backtest?**
- (a) *Recommended.* Values are shown now; strength is granted per signal only after its backtest. Why: effects decay after publication (McLean & Pontiff), and our version is time-series, not cross-sectional.
- (b) Strength from the literature now.

**6.4 Where do M09 values live?**
- (a) *Recommended.* History and reasons in `technical_signal`; the latest value per profile in D13 `signal`. Why: confluence reads one table, while backtests need NULL reasons and per-bar history.
- (b) D13 `signal` only, with a new reason column.
- (c) `technical_signal` only.

---

## Signals out
Grade A for everything computed from `price_bar` and FRED. "Lead" = drives the profile; "ctx" = context; "warn" = warning only (D16).

| Signal | Type / range | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| trend_state | up / flat / down (+1/0/−1), pending flag | Profile trend with 2-close hysteresis | ctx (M01 rule 1) | lead | ctx (10/50-day) |
| ma_distance | % vs 40-week MA | How stretched price is | ctx | ctx | ctx |
| mom_12_1 | return, NULL if < 53 weeks | 12-1 time-series momentum | ctx | lead | ctx |
| mom_12_7 | return | Intermediate momentum (Novy-Marx) | ctx | lead | – |
| hi52_ratio | 0–1 | Close ÷ highest daily adjusted close over 252 sessions | ctx | lead | ctx |
| rel_mom_spy | return difference | 12-1 vs SPY | ctx | lead | – |
| rev_1w, rev_1m | z by own volatility | Short-term reversal candidate | ctx | ctx | lead |
| news_context | none / earnings / news | News on the move's days | ctx | ctx | ctx |
| turnover_pctile | 0–100, own history | High = continuation more likely | – | ctx | ctx |
| earnings_gap | marker | Earnings move; drift expected | ctx | ctx | ctx |
| band_z | z of log price vs 20-week mean | M01 band depth (3.1) | lead (timing) | ctx | ctx |
| pullback_sigma | σ_w units | Depth from 20-week high in return σ | lead (timing) | ctx | ctx |
| band_trigger | event + cooldown | 1–2σ / beyond-2σ trigger with `qualified` | lead (rule 3/7) | – | – |
| vol_yz20, atr14, atr10w | annualized % / price units | Volatility panel | ctx | ctx | ctx |
| vol_regime | low / normal / high | Own 3-year percentile | ctx | ctx | ctx |
| market_regime | up / below_ma / bear / panic | SPY + VIX state; feeds M12 (R20) | ctx | warn (panic) | ctx |
| falling_knife | label | 12-1 < 0 and below a falling 40-week MA | warn | warn | – |
| range_state | pending Q2 | — | — | — | — |

## Build parts (proposal)
- Each part is one conversation at Medium effort, High only if a design question arises. Branches are `m09-part1` onward.
- **Each part:**
  - updates the M09 module doc (and DATA_SOURCES.md where relevant) in the same commit;
  - ships fixture tests.
- **Live check:** one per part. You run it on the real DB (Claude cannot read `data\`), it takes a few minutes, and you send back a small log.
- **Dependencies:** no new packages expected; FRED goes through the existing HTTP client.

| Part | Contents | Depends on | Live check (one per part) |
|---|---|---|---|
| 1 Plumbing and benchmark | Completed-bar reader (daily, weekly); `config/technicals.toml` with method versions; detail table + D13 writer (6.4) in the next free engine migration; SPY (± SMH) on the Tiingo list (6.1); FRED VIXCLS fetcher (key vs CSV checked); M09 step after prices; `stale` propagation | — | Refresh with SPY added (1 Tiingo request) + one VIXCLS fetch; first/last completed bar per symbol (SPCX, INFQ) |
| 2 Trend, momentum, regime | `trend_state` (2.3), `ma_distance`, `mom_12_1`, `mom_12_7`, `hi52_ratio`, `rel_mom_spy` (1.1, 1.3); `market_regime` (2.2); falling-knife label | 1 | Compute report vs this pack's MU, MSTR, SPY figures |
| 3 Volatility and bands | Volatility panel (3.2); `band_z`, `pullback_sigma`, empirical band (3.1, 3.3); true-range check; band trigger, cooldown and trigger log (4.3); `qualified` flag and `m09_qualify` items (4.1) | 1, 2 | Band and volatility values plus trigger log; MU 2026 pullbacks reproduced |
| 4 Short-term reversal and context | `rev_1w`, `rev_1m`; `news_context` from `event` and `news_item`; `earnings_gap`; turnover with same-date shares, `turnover_pctile` (1.2) | 1; M04 shares concepts if ready | Reversal values, news tags, turnover-missing reasons (META, MSTR, GOOG) |
| 5 Technicals tab and digest | Mock-up on stored data first (D-UI-4); overlays; per-profile state table; state-flip digest under the weekly cap; R17 wording (4.2) | 2–4 | You run the app on the real DB and comment |
| 6 Backtest and calibration | Walk-forward harness; hit rates and 26/52-week forward returns per signal; per-stock band hit counts; strength per signal (6.3); PT/ST rows into M01 (6.2); CvD split once M04 exists | 2–4 | Backtest report |
| 7 Range signals (Q2) | Only after 5.1/5.2: candidate-overlay mock-up, then the chosen definition | 1, 3 | Range states for the watchlist |

## Known gaps
1. **Not checked against primary text:**
   - Faber (SSRN 403);
   - the exact market-return windows in Cooper et al. and Daniel–Moskowitz;
   - De Bondt–Thaler's ~25% (the secondary page now returns 403);
   - Hurst et al.'s drawdown statistics (dropped);
   - Sullivan–Timmermann–White's rule count and out-of-sample years (FMG shows the abstract only).

   McLean & Pontiff's 26%/58% and Daniel–Moskowitz's loser betas above 3 were confirmed through abstract listings and search summaries.
2. All price figures are from Yahoo and must be recomputed from `price_bar`.
3. Analyst revisions (needed by Da, Liu & Schaumburg, and by M08's R15) are not free. This needs a new DATA_SOURCES entry, numbered after M04's proposed DS12–DS15.
4. INFQ's first stored bar is unchecked. SPCX's 12-1 momentum is unavailable until about June 2027.
5. M04's `qualified` inputs (CvD, survival gate, shares concepts) are not built.
6. Which watchlist names count as high turnover is unknown until turnover is computed. META, MSTR and GOOG share counts are missing.
7. Backtests cannot use news context before October 2026; they use 8-Ks only.
8. The tracked universe is theme-chosen, so no market-wide cross-section exists.

## New sources
Provisional IDs. They become SOURCES.md IDs after M04's S-new IDs (S122 onward) are assigned and the duplicate S101 is fixed. "Other" marks non-peer-reviewed or secondary sources.

- **S-new-M09-1** Lehmann (1990), "Fads, Martingales, and Market Efficiency", QJE 105(1):1–28 — https://ideas.repec.org/a/oup/qjecon/v105y1990i1p1-28..html ; Jegadeesh (1990), JF 45(3):881–898 (extends S12; citation via RePEc reference list). Conrad & Kaul (1993) and Ball, Kothari & Shanken (1995), long-term reversal critiques (secondhand).
- **S-new-M09-2** Medhat & Schmeling (2022), "Short-term Momentum", RFS 35(3):1480–1526 — https://openaccess.city.ac.uk/id/eprint/31278/
- **S-new-M09-3** Da, Liu & Schaumburg (2014), Management Science 60(3):658–674 — https://ideas.repec.org/a/inm/ormnsc/v60y2014i3p658-674.html ; Chan (2003), JFE 70(2):223–260 — https://academicnewsletter.sufe.edu.cn/info/357702
- **S-new-M09-4**
  - Novy-Marx (2012), JFE 103(3):429–453 — https://academicnewsletter.sufe.edu.cn/info/356869
  - Israel & Moskowitz (2013), JFE 108(2):275–301 — https://ideas.repec.org/a/eee/jfinec/v108y2013i2p275-301.html
  - George & Hwang (2004), JF 59(5):2145–2176, DOI 10.1111/j.1540-6261.2004.00695.x — https://academicnewsletter.sufe.edu.cn/info/361244
  - Moskowitz & Grinblatt (1999), JF 54(4):1249–1290 — https://ideas.repec.org/a/bla/jfinan/v54y1999i4p1249-1290.html
  - Du (2008), secondhand.
- **S-new-M09-5** Kenneth R. French Data Library factor definitions:
  - Mom (2-12) — https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html
  - ST_Rev (1-1) — https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_st_rev_factor.html
  - LT_Rev (13-60) — https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_lt_rev_factor.html
- **S-new-M09-6** Bernard & Thomas (1989), JAR 27 Suppl.:1–36 (figures via https://en.wikipedia.org/wiki/Post%E2%80%93earnings-announcement_drift, other); McLean & Pontiff (2016), JF 71(1):5–32 — https://ideas.repec.org/a/bla/jfinan/v71y2016i1p5-32.html ; abstract figures via https://academicnewsletter.sufe.edu.cn/info/359722
- **S-new-M09-7**
  - Brock, Lakonishok & LeBaron (1992), JF 47(5):1731–1764 — https://ideas.repec.org/a/bla/jfinan/v47y1992i5p1731-64.html
  - Sullivan, Timmermann & White (1999), JF 54(5):1647–1691 — https://www.fmg.ac.uk/publications/discussion-papers/data-snooping-technical-trading-rule-performance-and-bootstrap
  - Bajgrowicz & Scaillet (2012), JFE 106(3):473–491 — https://ideas.repec.org/a/eee/jfinec/v106y2012i3p473-491.html
- **S-new-M09-8**
  - Moskowitz, Ooi & Pedersen (2012), JFE 104(2):228–250 — https://papers.ssrn.com/abstract=2089463
  - Hurst, Ooi & Pedersen (2017), JPM 44(1), other — https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
  - Faber (2007), J. Wealth Management, other, unverified.
  - Kim, Tse & Wald, secondhand.
- **S-new-M09-9**
  - Cooper, Gutierrez & Hameed (2004), JF 59(3):1345–1365 — https://academicnewsletter.sufe.edu.cn/info/361185
  - Galariotis, Holmes, Kallinterakis & Ma (2014), IRFA 32:1–12.
  - Daniel & Moskowitz (2016), JFE 122(2):221–247 — https://www.nber.org/papers/w20439
- **S-new-M09-10**
  - Cont (2001), Quantitative Finance 1(2):223–236 — https://ideas.repec.org/a/taf/quantf/v1y2001i2p223-236.html
  - Parkinson (1980), J. Business 53(1):61–65.
  - Yang & Zhang (2000), J. Business 73(3):477–492 — https://scholars.cityu.edu.hk/en/publications/drift-independent-volatility-estimation-based-on-high-low-open-an/
  - Wilder (1978) ATR, other — https://en.wikipedia.org/wiki/Average_true_range
  - Bollinger Bands, other — https://en.wikipedia.org/wiki/Bollinger_Bands
- **S-new-M09-11**
  - Barroso & Santa-Clara (2015), JFE 116(1):111–120 — https://ideas.repec.org/a/eee/jfinec/v116y2015i1p111-120.html
  - Moreira & Muir (2017), JF 72(4):1611–1644 — https://www.nber.org/papers/w22208
  - DeMiguel, Martín-Utrera & Uppal (2024), JF 79(6) — https://lbsresearch.london.edu/id/eprint/3716 (cites Cederburg et al. and Barroso & Detzel).
  - Ang, Hodrick, Xing & Zhang (2006), JF 61(1):259–299 — https://www.nber.org/papers/w10852
- **S-new-M09-12** J.P. Morgan, "The Agony & the Ecstasy" (2014), other — https://www.chase.com/content/dam/privatebanking/en/mobile/documents/eotm/eotm_2014_09_02_agonyescstasy.pdf (R17)
- **S-new-M09-13** Osler (2000), "Support for Resistance", FRBNY Economic Policy Review 6(2):53–68 — https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.pdf ; Lo, Mamaysky & Wang (2000), JF 55(4):1705–1765 — https://web.mit.edu/~alo/www/Papers/techanal.html ; Fidelity, range trading, other — https://www.fidelity.com/learning-center/trading-investing/trading/range-trading (Q2)
- **S-new-M09-14** FRED VIXCLS (Cboe, internal use) — https://fred.stlouisfed.org/series/VIXCLS ; Yahoo Finance chart API, worked examples only, other — https://query1.finance.yahoo.com/v8/finance/chart/MU?range=2y&interval=1wk (likewise MSTR, SPY, TSLA)
