# M12 — Design review pack (draft for the owner)

**Status:** research only — nothing is decided until the owner answers (D7); 2026-10-12 · **Effort:** High for this review; Medium for each build part.

Outputs are research signals, not financial or tax advice.

**How to answer.** Reply in plain text, e.g. "1.1a 1.2a 2.1a …".
- To reject a suggestion, strike it by number ("S3.2 no"), or reply "rest ok".
- Your answers become decisions D-M12-1 onward.
- Every threshold here is a starting value.

**How claims are cited.**
- S-numbers come from SOURCES.md. Provisional IDs (S-new-M12-n) are listed under "New sources". Facts about the codebase cite the file.
- Grades: PR = peer-reviewed, WP = working paper, Primary = exchange, statute, vendor docs or company document, Other = practitioner or press.

## Purpose and dependencies
**Purpose.** For a stock you already hold, M12:
- shows when writing a covered call is a reasonable window;
- proposes an expiry and strike;
- keeps the overlay's assignment and tax facts in view.

It gives signals only and enforces nothing (R20). You decide (D8, D16).

**Approved items it must honour:**
- **R20 (modified).**
  - Covered-call window: regime weak or sideways, IV high against the stock's own history, no earnings inside the option's life.
  - Template: 30–45 DTE, about 15 delta, labelled "index-derived".
  - Tax and assignment notes are informational.
  - Round 5 proposes changing 30–45 to 31–45 DTE, under D6.
- **Core rules:**
  - D11: the overlay is judged under its own profile.
  - D12: each decision logs its profile, and each position keeps a profile of record.
  - D13 signal record, D14 evidence grades.
  - D10: every output is visible in every timeframe.
- **Scope and data limits:**
  - S1: options are in scope.
  - S2: free sources only.
  - D-UI-2 / S68: Tiingo data is for internal use only.
  - D-M02-12: the PC is off overnight, so every fetch runs in the logon catch-up, which is limited to 3 h.
- **R14 / S01:** wealth creation comes from a few big winners. This is the basis of the thesis block in Round 5.
- **Missing data stays missing,** never zero.
- **Q5** (free options data coverage) is answered in Round 2.

**Depends on (none of these is redesigned here):**

| Module | What M12 uses | State |
|---|---|---|
| M00 | `price_bar` with close, adjusted close and `div_cash` (`src/engine/prices/store.py`, migration 0012); Item 2.02 `event` rows (`services.earnings_dates`, `src/engine/ui/services.py`); `fetch_log` budgets; Massive `massive` lane (`src/engine/news/vendors.py`); UI | Built |
| M01 | Profiles; `lot_status`; 40-week moving-average trend filter; 1–2σ add trigger | MY profile reviewed (D27); no lot tables in code yet |
| M02 part 7a | IR news items (`news_item`, grade A), used for earnings-date notices | Merged |
| M04 | CvD and the survival gate (optional block) | Design pack in review |
| M09 / M10 | Regime | Not designed. Interim `regime_v0` (Round 5) |
| M11 | Thesis state, milestones, killswitch | Not designed. Until then the thesis block uses M01's add trigger |

---

## Round 1 — What the overlay may claim (index vs single-stock premium)

### What the research says
1. **Index premiums are strongly negative,** which means option sellers are paid (PR, S-new-M12-1).
   - Method: synthetic variance swaps on 5 indexes and 35 single stocks.
   - The result comes from the paper body, which was not re-read.
2. **The average single-stock premium is insignificant** (WP, S-new-M12-2; same research line as S31). Over 1996–2012:
   - S&P 500 members: a zero 30-day variance premium is not rejected for 503 of 919 stocks.
   - DJ30 (from 10/1997): not rejected for 27 of 43.
   - The index premium is large and comes from correlation risk: implied correlation averaged 39.5% against 32.5% realized.
   - Subperiods:
     - 1996–2001: the average single-stock premium was positive and significant at 30 days (not at 60 or 90 days).
     - 2002–07: "some evidence" against zero.
     - 2008–12: all average point estimates are negative.
   - This is the evidence behind R20's "index-derived" label.
3. **Delta-hedged S&P 500 options lose money on average,** and lose more when volatility is high (PR, S-new-M12-3).
4. **High idiosyncratic volatility goes with lower option returns** (PR, S-new-M12-4).
   - Delta-hedged equity option returns fall as the stock's idiosyncratic volatility rises.
   - Controlling for limits-to-arbitrage proxies cuts the relation by about 40%.
   - It is a cross-sectional finding with frictions, not an average premium.
   - Which watchlist names are high-idiosyncratic is a guess (MSTR, TSLA, SPCX) until measured from stored bars.
5. **A covered call is three exposures** (PR, S29):
   - Equity: most of the risk and return.
   - Short volatility: a Sharpe ratio "of nearly 1.0" but "only 10% of the risk".
   - Equity reversal: about 25% of the risk, with "little return in exchange".
6. **One sponsor-funded study favours covered calls** (Other, S-new-M12-22).
   - An OIC-funded study of ten widely held stocks, 2003–13, reports that covered calls and covered combinations generally beat long stock on four risk-adjusted measures.
   - Weak evidence: abstract only, small sample, sponsor-funded.
7. **The 15-delta and 30–45 DTE evidence is from the S&P 500 index (SPX), not single stocks.** BXMD writes 30-delta SPX calls (S28); tastylive tested SPX short calls by delta (S30).

### Worked example (FRED copies of Cboe series, 2026-10-08; S-new-M12-9)
| Series | 30-day implied volatility (IV) | 1-year rank |
|---|---|---|
| VIX (S&P 500) | 15.41 | 11.0 |
| VXAPL (Apple) | 27.90 | 54.2 |
| VXAZN (Amazon) | 41.42 | 56.6 |
| VXGOG (Google) | 37.91 | 56.5 |

- Index IV is near its one-year low, while single-stock IV is mid-range. AAPL's reading includes its Nov-2 earnings.
- One day does not measure the correlation premium; that needs implied against realized correlation over time.
- It does show why the engine must not borrow the index's "cheap or rich" reading for a single stock.

### All cases
- **Name with a Cboe single-stock VIX** (AAPL, AMZN, GOOG): its own premium can be measured from 2010.
- **Name with only our own IV snapshot:** measurable once enough history is collected. Until then it shows "insufficient history".
- **New listing (SPCX):** no history. Only the claim line is shown.
- **Name measured as high idiosyncratic volatility:** gets the Cao & Han note (1.2).
- **Own measured premium negative over the last 12 months:** shown. What it does to the window depends on 1.1.
- **ETV (closed-end buy-write fund):** decided by 2.3.
- **Index readings (VIX, VXN):** shown as market context only, never as a stock's premium.

### Suggestions
- **S1.1 Label and claim line.** Every M12 template field carries `basis: "index-derived"`, and every signal carries the claim line: "Single-stock options carry little volatility premium on average (S-new-M12-2); this window is a timing signal, not an expected edge."
- **S1.2 Per-name premium history (`vrp_hist`).** iv30 minus the following 30-day realized volatility, wherever IV history exists. Shown by year with its sample size. Never extrapolated from the index.
- **S1.3 No expected return.** The signal carries no expected-return number. It shows the premium received and the upside given up instead (Rounds 5 and 6).

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Premium from index backtests | Read as if it applies to a single stock | "index-derived" label on every template field (R20); claim line |
| Full-sample averages | Hide subperiods: positive in 1996–2001, negative estimates in 2008–12 (S-new-M12-2) | The name's own premium history shown by year, with n |
| Premium before costs | Can disappear in bid-ask spreads (S-new-M12-2, S-new-M12-4) | "Before costs" label; contract volume shown |
| Short-volatility Sharpe of about 1 | Read as "covered calls are good", but that part is only about 10% of the risk, and the reversal part is about 25% of the risk with little return (S29) | Claim line; forgone-upside line (Round 6) |

### Questions
**1.1 How a name's own measured premium is used**
- (a) *Recommended.* Shown as context only; it never opens or closes the window. Why: the histories are short and noisy, and the average single-stock premium is insignificant.
- (b) The window opens only if the name's own premium was positive over the last 12 months.
- (c) Not used.

**1.2 Note for high idiosyncratic volatility**
- (a) *Recommended.* Yes: a separate note citing Cao & Han, with its friction caveat. Why: it is the only peer-reviewed evidence of a larger premium on some names.
- (b) No note.

---

## Round 2 — Options data and our own IV history (Q5, DS5)

### What the research says
1. **FRED: Cboe single-stock VIX series** (Primary, S-new-M12-9).
   - Free daily closes: `VXAPLCLS`, `VXAZNCLS` and `VXGOGCLS` from 2010-06-01, plus `VIXCLS` and `VXNCLS`. The last observation at the check was 2026-10-08.
   - Terms: "Copyright, 2016, Chicago Board Options Exchange, Inc. Reprinted with permission." FRED asks users to review this before sharing.
   - Covers 3 of the 15 operating watchlist names.
2. **Alpha Vantage:** `REALTIME_OPTIONS` and `HISTORICAL_OPTIONS` are premium functions, so not available on the free key (Primary, S-new-M12-10).
3. **Massive Options Basic** (Primary, S-new-M12-11).
   - $0, individual use, end-of-day data, 5 calls per minute, 2 years of history.
   - The daily ticker summary (`/v1/open-close/{optionsTicker}/{date}`: open, high, low, close, volume) is included in Basic.
   - The pricing page lists "Reference data" in Basic. Access to the endpoint still needs confirming.
   - The chain snapshot with Greeks, IV and open interest needs Starter or above ($29/mo, 15-minute delay).
   - So the free route is to compute IV ourselves from each contract's close. Because history covers 2 years, the logon run can backfill days missed while the PC was off.
4. **Alpaca** (Primary, S-new-M12-12).
   - The chain snapshot returns Greeks and IV.
   - The free "indicative" feed is derived from OPRA: quotes are modified and trades are delayed 15 minutes.
   - History only from February 2024.
   - Needs an account that you would open. S70 already records "no redistribution".
5. **Tradier:** the sandbox has delayed options but no Greeks. Greeks (from ORATS) need a brokerage account (Primary, S-new-M12-13). Schwab's Trader API needs a brokerage account plus a developer app; cost not confirmed.
6. **Cboe website quotes are excluded** (Primary, S-new-M12-14). The terms allow viewing and one personal copy, but "You may not otherwise copy, reproduce, alter, store either in hard copy or in an electronic retrieval system" without consent. A daily snapshot database is that kind of storage.
7. **Rejected or unconfirmed:**
   - yfinance stays rejected (S70).
   - Finnhub's option chain is not confirmed and is probably paid; to probe.
8. **SPCX.** It listed on 2026-06-12, and its options were set to start on 2026-06-16 (Other, S-new-M12-20). No source can give SPCX a 1-year IV history before about June 2027.

**Codebase**
- There is no FRED client yet. M01 also plans to use FRED (CPI, M2), so one shared client serves both.
- The Massive key and lane exist.
- `fetch_log` already does budget accounting (LESSONS: count limits, shared budgets).

**Route per name**

| Names | Route | Grade |
|---|---|---|
| AAPL, AMZN, GOOG | FRED copies of Cboe indexes, history from 2010 | A (computed by the exchange) |
| TSLA, MU, MSTR, SPCX, MSFT, BA, NVDA, GFS, INTC, META, MRVL | Our own snapshot from Massive Basic closes | B (computed by the engine) |
| INFQ, ETV | Option listing not verified; ETV is a closed-end fund | n/a until probed |

**Budget.** These are assumptions, not measurements.
- Per name per day: about 1 contract-list call plus 4 daily summaries (at-the-money (ATM) call and put × 2 expiries around 30 days).
- 12 names × 5 calls = 60 calls, about 12 minutes at 5 per minute, shared with the news `massive` lane.
- Backfill: 2 years ≈ 12 × 504 days × 4 contracts ≈ 24,000 calls ≈ 80 h. 1 year ≈ 40 h.
- At no more than 3 h per logon run (D-M02-12), either depth takes weeks of runs.

**What computing IV from closes needs:**
- Underlying close: Tiingo.
- Risk-free rate: FRED `DTB3` or `DGS1MO`.
- Dividends: Tiingo `div_cash`, projected forward.
- An American-exercise model (Cox-Ross-Rubinstein (CRR) binomial), or a call-put pair to back out the forward price.

### Worked example
- **AAPL, 2026-10-08.** VXAPL = 27.90 (real).
  - The probe computes our own 30-day IV from the closes of the Nov-6 and Nov-20 ATM AAPL contracts (Massive Basic).
  - Suppose it gives 28.6 (illustrative). That is a 0.7-point method gap, stored as the calibration row.
- **SPCX.** Options trade from 2026-06-16, so there are about 80 trading days by 2026-10-12. It shows "insufficient history (80/252)", never 0.

### All cases
- **A Cboe index exists (grade A):** never spliced with our own snapshot.
- **Own snapshot, both contracts traded:** normal case.
- **One contract (call or put) with zero volume:** IV from the other one only, flagged.
- **Both contracts with zero volume, or no pair of expiries around 30 days:** that day is missing.
- **Call IV and put IV differ by more than X points:** flagged as stale.
- **Dividend payer** (American early exercise matters) vs non-payer.
- **Day missed while the PC was off:** backfilled if within 2 years, otherwise stays missing.
- **Market holiday:** no row, and not counted as missing.
- **Adjusted contracts after a split or special dividend:** excluded.
- **New listing:** shows the "insufficient history" count.
- **No listed options, or a closed-end fund:** n/a.
- **Shared lane budget runs out mid-run:** resumes at the next logon; a partial day stays missing.
- **Vendor terms or plan change:** terms re-checked at each probe (D-M02-59 pattern).

### Suggestions
- **S2.1 Shared FRED client.** `src/engine/macro/fred.py`, or wherever M01 puts it. Series list in `config/m12.toml`.
- **S2.2 Own snapshot, `src/engine/options/snapshot.py`.**
  - Fetches Massive Basic daily summaries for the ATM call and put at the two expiries around 30 calendar days.
  - Solves IV by bisection on a CRR binomial model.
  - Stores `iv_obs(symbol, date, method, expiry, strike, cp, opt_close, opt_volume, und_close, rate, div_model, iv)` and a derived `iv30(symbol, date, source, value, n_contracts)`.
  - Budget through `fetch_log`, lane `massive`. The logon catch-up backfills missed days.
- **S2.3 Docs.** Add DS5 rows to DATA_SOURCES.md with each source's terms. Add a LESSONS line: "a site's personal-use clause can forbid storage even when viewing is free."
- **S2.4 One-off probe, `scripts/probe_options.py` (you run it).** It checks:
  - AAPL IV from one date's Massive Basic closes against VXAPL (our method error);
  - whether INFQ and ETV have listed options;
  - access to the contract-reference endpoint;
  - free access to Alpha Vantage `EARNINGS_CALENDAR` and to Finnhub (one call each).
- **S2.5 Close DESIGN Q5** with your answer to 2.1.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Last-trade option close | Hours stale against the 4:00 pm stock close on an illiquid contract | Volume > 0; average the call and put IVs; flag when they differ by more than X points |
| Dividends and American exercise | Bias IV on dividend payers | Forward price from the call-put pair; binomial model; dividend source shown |
| Alpaca indicative quotes | The quotes are "modified" | Grade B, never A |
| Vendor terms | Change without notice | Terms re-checked at each probe (D-M02-59) |
| Mixed-source history | FRED index readings and our own IV are not comparable | One source per name per series; never spliced |
| Missing day | Read as zero or forward-filled | Stays missing |
| New listing | A rank computed on a few days | "Insufficient history (n/252)" |

### Questions
**2.1 IV source for names with no Cboe index**
- (a) *Recommended.* Our own snapshot from Massive Basic closes. Why: free, grade B, about 12 minutes a day, no new account.
- (b) Alpaca indicative snapshots. Needs an account you open; history only from February 2024.
- (c) Massive Starter at $29/mo, once S2 is relaxed.
- (d) Your broker's API, if you hold Schwab or Tradier. Which broker do you use?

**2.2 Backfill depth for our own snapshot**
- (a) *Recommended.* 1 year (about 40 h of budget, spread over weeks). Why: a rank is available sooner.
- (b) 2 years (about 80 h).
- (c) Forward only; the rank becomes valid after 252 trading days.

**2.3 ETV (closed-end buy-write fund)**
- (a) *Recommended.* No options signals; shown as a real-world reference for an index buy-write. Why: it writes calls itself and has no earnings.
- (b) Treated like the other names.

---

## Round 3 — "IV high against its own history": rank, percentile, implied vs realized

### What the research says
1. **The common definitions are practitioner rules, not peer-reviewed** (Other, S-new-M12-17).
   - IV rank = (current − 52-week low) ÷ (52-week high − 52-week low) × 100.
   - IV percentile = the share of the last 252 days with IV below today's.
   - The rank's range moves whenever a new high or low is set. A spike does not create a new upper bound for the percentile.
   - Rule of thumb: an IV rank above 50 "can be indicative of an attractive opportunity to sell options".
2. **The peer-reviewed form of "IV is high" is IV against realized volatility** (PR, S-new-M12-5).
   - Sorting stocks on historical volatility minus ATM implied volatility gives significant monthly option returns. Options whose IV is high relative to realized volatility are overpriced.
   - A later transaction-cost critique (Do, Foster & Gray 2016) is known only second-hand.
3. **The index premium is larger when volatility is high** (PR, S-new-M12-3).
4. **Earnings inflate the reading.** A single stock's 30-day IV includes scheduled earnings variance whenever an announcement falls inside the 30 days (PR, S-new-M12-7). This raises rank and percentile before every print. The VXAPL drops after each Apple print (Round 4) illustrate it.

**Data needed:**
- Rank and percentile from `iv30`.
- Realized volatility from stored Tiingo bars (close-to-close, over 20 and 60 days).
- Earnings dates from Round 4, to tag the days whose 30-day window contains an announcement.

### Worked example (real FRED values, 252 observations to 2026-10-08)
| Name | 30-day IV | 1-year low (date) | 1-year high (date) | Rank | Percentile |
|---|---|---|---|---|---|
| AAPL (VXAPL) | 27.90 | 18.57 (2025-12-24) | 35.77 (2026-03-30) | 54.2 | 54.2 |
| AMZN (VXAZN) | 41.42 | 25.82 (2025-12-26) | 53.36 (2026-02-05) | 56.6 | 68.5 |
| GOOG (VXGOG) | 37.91 | 26.54 (2025-12-24) | 46.68 (2025-10-16) | 56.5 | 69.3 |
| SPX (VIX) | 15.41 | 13.47 (2025-12-24) | 31.05 (2026-03-27) | 11.0 | 17.1 |

- **AMZN** shows how far rank and percentile can differ: rank 57, percentile 69.
- **AAPL's** 27.90 already contains the Nov-2 earnings within its 30 days. An ex-event reading would be lower, so the plain percentile overstates "high".
- **`iv_rv_gap`** needs AAPL's realized volatility from stored bars, which Claude cannot read. Illustrative: a 20-day realized volatility of 22.0 gives a gap of +5.9.

### All cases
- **252 or more observations:** rank and percentile.
- **126–251 observations:** percentile labelled "provisional".
- **Under 126 observations:** "insufficient history (n/252)".
- **Today's 30-day window contains earnings:** ex-event IV if the term structure allows the split; otherwise flagged.
- **History contains event days:** excluded or kept, per 3.2, with the count shown.
- **One spike sets the 52-week high:** rank is depressed while percentile is unaffected, so both are shown.
- **IV high because the risk is real** (non-reliance under Item 4.02, bankruptcy under Item 1.03, going concern, lawsuit, merger): the window is blocked in Round 5.
- **Structural change** (e.g. MSTR's bitcoin treasury): 1-year and 3-year percentiles shown side by side where 3 years exist. That is the FRED names now; own-snapshot names only after 3 years of collection.
- **IV above realized but percentile low, or the reverse:** both tests shown separately.
- **Realized volatility has missing bars:** the value is missing.
- **Source changes:** the series is not spliced.

### Suggestions
- **S3.1 Signals:**
  - `iv_rank_252` and `iv_pct_252`, each with `n_obs`;
  - `iv_rv_gap` = iv30 − trailing 20-day realized volatility, in the Goyal–Saretto direction;
  - `iv_event_share`: the share of iv30 variance from scheduled earnings, when two expiries allow the split (Round 4).
- **S3.2 "IV high" for the window:** percentile ≥ 50 on ex-event days (or ex-event IV), and `iv_rv_gap` > 0.
- **S3.3 Horizons and thresholds:**
  - 30-day IV is compared with both the trailing and the following 30-day realized volatility, annualised on the same 252-day basis.
  - Below 252 observations: "insufficient history". From 126: a provisional percentile.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| IV rank | Driven by one spike, e.g. an earnings day | Percentile shown beside rank; event days excluded or ex-event IV |
| "High IV" | High because the risk really is high (lawsuit, FDA, merger) | M02/M04 event flags shown beside it; Item 4.02, Item 1.03 or a going-concern item blocks the window |
| 1-year window | Stale after a structural change (MSTR) | 1-year and 3-year percentiles together where 3 years exist |
| IV minus realized | Compares different horizons | 30-day against 30-day, same annualisation |

### Questions
**3.1 Which "high" test opens the window**
- (a) *Recommended.* Percentile ≥ 50 and IV above trailing realized volatility. Why: one practitioner test plus one peer-reviewed test.
- (b) Rank ≥ 50 only (the R20 wording).
- (c) IV minus realized only.

**3.2 Earnings-inflated days in the 252-day history**
- (a) *Recommended.* Excluded from the distribution, marked, with the count shown. Why: otherwise every pre-print day looks "high".
- (b) Kept.

**3.3 Threshold**
- (a) *Recommended.* 50. Why: the practitioner rule of thumb (S-new-M12-17).
- (b) 70.
- (c) You set it per profile.

---

## Round 4 — Event calendar: no earnings inside the option's life, plus an ex-dividend check

### What the research says
1. **Option sellers lose around earnings** (PR, S-new-M12-6).
   - At-the-money straddles held from 3 days before earnings to the announcement return 3.34%, so sellers lose.
   - Investors underestimate announcement uncertainty, more so for small, volatile, high-kurtosis names.
   - This supports R20's earnings exclusion.
2. **Event variance can be separated** (PR, S-new-M12-7). Option-implied earnings uncertainty is large, varies over time and predicts future volatility. The paper gives a method to split event variance from normal daily variance.
3. **Alpha Vantage `EARNINGS_CALENDAR`** returns "company earnings expected in the next 3, 6, or 12 months" (Primary, S-new-M12-10).
   - Without `symbol` it returns all companies, as CSV.
   - It carries no premium tip, but free access was not tested.
4. **Companies announce their dates on IR sites** (S-new-M12-18).
   - Apple set fiscal Q4 2026 results for Monday 2026-11-02, call at 2:00 pm PT (reported from Apple IR).
   - Part 7a already polls IR RSS feeds (grade A).
5. **Early assignment before an ex-dividend date** is likely when the dividend exceeds the call's remaining time value (Other, S-new-M12-16, Fidelity).
   - Using the same-strike put as a proxy for that time value is a standard check, but the Schwab page that covers it could not be read.
   - Background on call holders failing to exercise optimally: S-new-M12-8 (bibliographic only).
6. **Finnhub's earnings calendar:** free access not confirmed.

**Data available:**
- **Past dates:** Item 2.02 `event` rows (`services.earnings_dates`). These also let the engine estimate the next date from each company's cadence.
- **Announced dates:** IR news items (`src/engine/news/`). Needs a parser for notices such as "to announce … results on <date>".
- **Vendor calendar:** Alpha Vantage, 1 request per week with no symbol, sharing the transcripts budget (the scheduled run uses 20 of the 25 daily requests).
- **Dividends:** past ex-dates from Tiingo `div_cash`; upcoming ex-dates only from declaration releases (IR or 8-K text). No structured free source was verified.

### Worked example
**Apple's IV drop after earnings** (FRED VXAPL; dates from Apple releases, S-new-M12-18; check 2025-10-30 against the stored 8-K)

| Announcement | VXAPL that day | Next day | Change |
|---|---|---|---|
| 2025-10-30 | 27.65 | 24.76 | −10.5% |
| 2026-01-29 | 34.81 | 28.05 | −19.4% |
| 2026-04-30 | 31.01 | 25.30 | −18.4% |
| 2026-07-30 | 32.01 | 28.45 | −11.1% |

**AAPL window on 2026-10-08.** Next earnings 2026-11-02 (grade A).
- The 2026-11-20 monthly (43 DTE) contains Nov 2, so it is blocked.
- The 2026-10-30 weekly (22 DTE) is outside the template.
- Result: `cc_window = blocked_earnings` until 2026-11-03. The first eligible monthly is then 2026-12-18 (45 DTE).

**SPCX first print** (Other, S-new-M12-19; article dated 2026-07-30, quotes from 2026-07-29 before the open)
- Earnings on 2026-08-04, after the close.
- ATM IV: about 129% (Jul 31 expiry), 156% (Aug 7), 122% (Aug 21), 101% (Sep 18).
- Realized volatility: 55.0% (10 days), 59.4% (20 days), 95.3% since listing.
- Implied move by Aug 7: 19.8% (the 116 straddle ≈ $23.05 on a $116.41 share price).
- **Event split (computed by Claude on calendar days; the base rate is an assumption):**
  - Total variance to Aug 7 = 1.56² × 9/365 = 0.0600.
  - Variance to Jul 31 = 1.29² × 2/365 = 0.0091.
  - Base variance for the remaining 7 days = 1.29² × 7/365 = 0.0319.
  - Event variance = 0.0600 − 0.0091 − 0.0319 ≈ 0.019, about a 13.8% one-day move. A lower base gives a larger event move.
- Rule result: blocked; IV rank = insufficient history.

### All cases
- **Date confirmed by an IR notice falls inside the option's life:** blocked (grade A).
- **Vendor date only:** blocks or warns per 4.1 (grade B).
- **Date estimated from cadence:** blocks ±7 days around the estimate (grade C).
- **Results after the close on expiry Friday, or before the open on the next Monday:** the block extends to expiry + 1 trading day.
- **Unknown time of day:** treated as blocking for that day.
- **Date moves after a signal was issued:** re-checked daily; an alert is raised.
- **Sources disagree:** newest confirmed date wins; review item `m12_date_conflict`.
- **First print with no history (SPCX):** closed until after the print.
- **No earnings within 45 days:** no earnings block.
- **Ex-dividend date before expiry:** `assignment_risk` (4.2).
- **Other scheduled events** (SPCX lock-up expiry, investor days, FDA): per 4.3.
- **ETV:** no earnings; n/a.

### Suggestions
- **S4.1 Event table.** `m12_event(symbol, kind ∈ {earnings, ex_div, other}, date, time ∈ {bmo, amc, dmh, unknown}, status ∈ {confirmed, vendor, estimated}, grade, source_ref)`. The newest confirmed row wins; disagreements go to `m12_date_conflict`.
- **S4.2 Notice parser** on IR items: regex first; you confirm the first 10 hits.
- **S4.3 Weekly vendor pull.** One Alpha Vantage `EARNINGS_CALENDAR` request with no symbol, filtered to watchlist and tracked names.
- **S4.4 Window rule.**
  - `blocked_earnings` if any earnings row falls in [today, expiry + 1 trading day].
  - `assignment_risk` if an ex-dividend date falls before expiry. The put-against-dividend check needs chain data, so it is grade B.
- **S4.5 Event-variance split** (S-new-M12-7) when two expiries straddle the date, stored as `iv_event_share`.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Vendor earnings date | Wrong or unconfirmed | Grade A only from the company; vendor B; cadence estimate C; an estimate blocks ±7 days |
| Announcement timing | After the close on expiry Friday, or before the next open | Block up to expiry + 1 trading day |
| Date changed | The issued signal goes stale | Daily re-check; alert on change |
| Other events | Lock-ups, investor days or FDA dates missed | Optional `other_events` list from M02 news, curated by you |
| First print | No base rate | Window closed until after the print |
| Ex-dividend in the option's life | Early assignment | `assignment_risk` flag (information, not a block) |

### Questions
**4.1 Earnings-date sources**
- (a) *Recommended.* IR notice (A) > Alpha Vantage calendar (B) > cadence estimate (C), and every status blocks. Why: the cost of being wrong is the event risk S-new-M12-6 measures.
- (b) Only confirmed dates block; estimates only warn.

**4.2 Ex-dividend inside the option's life**
- (a) *Recommended.* A warning with the dividend amount and an early-assignment note. Why: it is a cost to manage, not a reason to skip.
- (b) Blocks like earnings.

**4.3 Other scheduled events (lock-ups, investor days)**
- (a) *Recommended.* A list you curate, warning only. Why: there is no reliable free feed.
- (b) Ignored in v1.

---

## Round 5 — The covered-call window and strike template

### What the research says
1. **The tax test needs more than 30 days** (Primary, S-new-M12-15). A qualified covered call must be "granted more than 30 days before" expiry (26 USC 1092(c)(4)(B)). R20's "30–45 DTE" includes day 30, which fails that test. Proposed template: **31–45 DTE**.
2. **The 15-delta default comes from SPX evidence** (S28, S30). Single stocks have a different volatility skew, so a strike found from ATM IV is not a true 15-delta strike.
3. **The regime condition is the owner's rule, not a sourced edge** (S29).
   - The equity-reversal exposure is uncompensated.
   - None of the sources read supports timing covered-call writes by regime.
   - No peer-reviewed study was found showing that a trend or sideways filter improves single-stock covered calls.
   - So "weak/sideways" is labelled as R20's rule.
4. **Capping a long-term winner is costly** (PR, S01, R14). Wealth creation is concentrated in a few big winners. This argues for blocking the window when the MY thesis is "accumulate" or the stock is in M01's entry or add zone.

**Data available:**
- Regime inputs exist: weekly bars and M01's 40-week moving average.
- M09 and M10 are not designed, so v1 needs an interim rule.
- The strike needs iv30, the stock's close, a rate (FRED) and a dividend yield (Tiingo).
- The listed-strike grid comes from Massive reference data, if the probe confirms access. Otherwise strikes are rounded to standard increments and labelled "assumed".

### Worked example
**AAPL arithmetic only** (the window itself is blocked by earnings in Round 4). Inputs:
- S = 340.42, AAPL's close on 2026-10-08 (S-new-M12-21). This was checked once against a public chart feed that is rejected for engine use, so the build uses the stored Tiingo bar.
- σ = 27.9% (VXAPL); T = 43/365.
- Rate 4.0% and dividend yield 0.3% (both illustrative).

Results:
- The 15-delta strike is about 379.3, 11.4% out of the money.
- Black-Scholes value is about $2.43 per share.
- The risk-neutral probability of finishing in the money is about 12.9%.
- With an assumed listed strike of $380 (illustrative), the record reads "approx., skew not modelled, index-derived".

**MU (illustrative).** Suppose:
- the weekly close is below the 40-week moving average;
- the IV percentile is 72;
- there are no earnings inside the option's life.

That would open the window. But if M04's CvD = CYCLICAL_TROUGH and M01's add trigger is active, the state becomes `blocked_thesis`.

### All cases
- **Every test passes:** `open`, after 2 consecutive passing days.
- **Regime up:** `closed_regime`.
- **IV not high:** `closed_iv_low`.
- **Earnings inside the option's life:** `blocked_earnings`.
- **Item 4.02, Item 1.03, going concern, or an M04 survival-gate fail:** `blocked_event`.
- **MY thesis "accumulate", or M01's add trigger active:** `blocked_thesis`.
- **IV history too short (SPCX):** `insufficient_data`.
- **Several reasons at once:** one state, with the full reason list.
- **Input module not built yet** (M04 gate, M11 thesis): that test shows "not evaluated", never "passed".
- **No monthly expiry in 31–45 DTE:** a weekly expiry.
- **No listed-strike grid:** rounded strike, labelled "assumed".
- **Holding below 100 shares, or no holding:** window still shown (D10); template marked "not coverable".
- **Window flickering day to day:** hysteresis.

### Suggestions
- **S5.1 Window states.** `cc_window` ∈ {`open`, `closed_regime`, `closed_iv_low`, `blocked_earnings`, `blocked_event`, `blocked_thesis`, `insufficient_data`}, each with a reason list.
  - When several apply, the state shown follows this order: blocked_event > blocked_thesis > blocked_earnings > insufficient_data > closed_regime > closed_iv_low.
- **S5.2 Interim `regime_v0`** for "weak/sideways": either
  - the weekly close is below the 40-week moving average, or
  - the moving-average slope is within ±X% over 10 weeks and the 26-week return is within ±Y%.

  X and Y are yours to set; no sourced values were found. Labelled "provisional; replaced by M09".
- **S5.3 Template.**
  - Expiry: the standard monthly in 31–45 DTE, or a weekly if no monthly fits.
  - Strike: the first listed strike at or above the approximate 15-delta value.
  - Shown: premium, % out of the money, upside cap, and risk-neutral probability of finishing in the money. All labelled "index-derived".
- **S5.4 Hysteresis.** The window opens after 2 consecutive passing days and closes on the first failure. Each day's recompute is logged.
- **S5.5 Evidence grade.** The grade of `cc_window` is the lowest grade among the inputs that decided it.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Interim regime | Taken for M09's future rule | Labelled `regime_v0`, replaced when M09 lands |
| Strike from ATM IV | Skew ignored, so the real delta differs | "Approximate; skew not modelled" |
| Probability of finishing in the money | Read as a real-world probability | "Risk-neutral" label |
| Window state | Flickers daily | Hysteresis; daily recompute log |
| Regime filter | Read as a proven edge | "Owner rule (R20), not a sourced edge" label |

### Questions
**5.1 DTE template**
- (a) *Recommended.* 31–45 DTE. Why: keeps the qualified-covered-call status (26 USC 1092(c)(4)(B)); this changes R20 under D6.
- (b) Keep 30–45 as approved.

**5.2 Interim regime before M09**
- (a) *Recommended.* `regime_v0` as in S5.2, labelled provisional, with X and Y from you. Why: honours R20 now without pretending to be M09.
- (b) No regime test until M09; only the IV and event tests.
- (c) A market regime based on the VIX (an M10 preview).

**5.3 Block when the MY thesis says accumulate, or M01's add trigger is active**
- (a) *Recommended.* Yes, block. Why: R14; it avoids capping future winners.
- (b) Warning only.

---

## Round 6 — Overlay accounting, assignment and tax notes (informational, D11)

### What the research says
1. **What makes a covered call qualified** (26 USC 1092(c)(4); Primary, S-new-M12-15):
   - Exchange-traded.
   - Granted more than 30 days before expiry.
   - Not "deep-in-the-money".
     - Deep-in-the-money means a strike below the "lowest qualified bench mark": the highest available strike below the applicable stock price, generally the prior close.
     - For options granted more than 90 days before expiry with strikes above $50, the benchmark is the second-highest strike below that price.
     - Floors apply at stock prices of $25 or less (85% of the price) and $150 or less (the price minus $10).
2. **Year-end rule, (c)(4)(E).** The exception does not apply when all of these hold:
   - the calls are closed, or the stock is sold, at a loss in one year;
   - the gain on the other position falls in a later year;
   - the remaining stock or option was not held 30 days or more after that closing or sale.
3. **§1092(f):** an in-the-money qualified call suspends the stock's holding period while the call is open. A loss on the call is long-term if a gain on the stock would have been.
4. **Fidelity on covered-call tax** (S26):
   - On assignment, the sale price is the strike plus the net premium.
   - An expired call's premium is a short-term gain.
   - A non-qualified covered call on stock held less than a year ends its holding period.
   - Qualified dividends need 61 days held within a 121-day window; the suspension caused by an in-the-money qualified call can break that.
5. **IRS Pub 550** has the sections "Qualified covered call options and optioned stock" and "Wash Sales > Options and futures contracts". The body text was not read (S-new-M12-15).
6. **D11 and M01.** A holding is core lots plus optional overlays, each judged under its own profile. M01 tracks `lot_status` (<1 yr / ≥1 yr). No lot or overlay tables exist in code yet.

### Worked example (illustrative lots, real rules)
| Lot | Bought | Shares | Status on 2026-11-03 |
|---|---|---|---|
| L1 | 2025-06-10 | 200 | ≥1 yr |
| L2 | 2026-03-02 | 100 | <1 yr; turns long-term 2027-03-03 |

- **Overlay:** 3 × AAPL Dec-18-2026 calls, written 2026-11-03.
  - 45 DTE is more than 30 days. With the strike out of the money, it is not deep in the money, so the call qualifies.
  - Out of the money at grant, so the holding period continues.
- **Assignment on 2026-12-18 under FIFO** delivers L1 (200 shares) and L2 (100 shares).
  - Warning: "L2 <1 yr: short-term gain; turns long-term 2027-03-03, after expiry."
- If Apple declares an ex-dividend date before Dec 18, the early-assignment note is added.

### All cases
- **Out of the money at grant and more than 30 DTE:** qualified; holding period continues.
- **In the money at grant but at or above the benchmark:** qualified; holding period suspended (§1092(f)).
- **Strike below the lowest qualified benchmark:** deep in the money, not qualified.
- **30 DTE or less:** not qualified.
- **Roll up and out:** a new grant; every check is re-run.
- **More contracts than linked shares ÷ 100:** refused as "covered".
- **FIFO would deliver lots under 1 year, or lots that turn long-term before expiry:** warning.
- **Ex-dividend inside the option's life:** early-assignment note; the 61/121-day note if the call is in the money.
- **Call closed at a loss in December with the stock gain in the next year:** (c)(4)(E) 30-day note.
- **Call expires worthless:** premium is a short-term gain (S26).
- **Call bought back:** the result goes to the overlay ledger.
- **Partial assignment:** the lots delivered are shown.

### Suggestions
- **S6.1 Overlay tables.** `overlay_position` and `overlay_lot_link`.
  - The overlay keeps its own profile of record (D12), "M12 overlay (ST)", separate from the core MY profile.
  - Lot tables are shared with M01; if M01 has not built them, this part builds them.
- **S6.2 Tax and assignment panel (informational):**
  - Qualified-call check: DTE > 30, and strike at or above the benchmark from the prior close and the listed strikes.
  - In-the-money-at-grant flag, which means the holding period is suspended.
  - Lots under 1 year, with the date each turns long-term.
  - Lots FIFO would deliver.
  - Ex-dividend date and dividend against put value.
  - The December 30-day note.
  - An "informational, not tax advice" banner with statute links.
- **S6.3 Lot warnings.** A warning, never a block, when assignment would deliver lots under 1 year or lots that turn long-term before expiry.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Tax notes | Read as tax advice | Banner; statute and source links |
| Assignment lots | The broker's default (often FIFO) delivers lots you did not intend | FIFO lots and their status shown; you choose specific identification at the broker |
| Contract count | An uncovered call recorded as covered | Contracts ≤ floor(linked shares ÷ 100), otherwise refused |
| Roll | The new grant is in the money or 30 DTE or less | Qualified-call checks re-run on every roll |
| Overlay P&L | Netting it into core performance hides the capped upside | Separate overlay ledger plus a "forgone upside" line (stock gain above the strike) |

### Questions
**6.1 Lot selection shown**
- (a) *Recommended.* FIFO and specific-ID views side by side. Why: shows what the broker default would do and the alternative you can choose.
- (b) FIFO only.
- (c) You tag the eligible lots per position.

**6.2 Overlay P&L reporting**
- (a) *Recommended.* A separate overlay ledger plus forgone upside, with a combined view on request. Why: S29's capped upside stays visible.
- (b) Combined with core only.

**6.3 Wash-sale notes**
- (a) *Recommended.* Read Pub 550 at build and add only what it states. Why: its body text has not been read yet.
- (b) Left out of v1.

---

## Signals out (proposed D13 signals)
All signals are visible in every timeframe (D10); the profile changes only their weight.

| Signal | Type / range | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| `cc_window` | State (S5.1) + reasons | Covered-call window | Shown; low weight | Medium | Primary |
| `cc_template` | Expiry, strike, premium, % OTM, upside cap, risk-neutral probability ITM | Proposed write; "approx., index-derived" | Shown | ✓ | ✓ |
| `iv30` | % + source + grade | 30-day IV (Cboe or our own) | Context | ✓ | ✓ |
| `iv_rank_252` / `iv_pct_252` | 0–100 + n_obs, or "insufficient (n/252)" | IV against its own history | Context | ✓ | ✓ |
| `iv_rv_gap` | IV points | IV minus trailing realized volatility | Context | ✓ | ✓ |
| `iv_event_share` | 0–1 | Share of IV from scheduled earnings | Context | ✓ | ✓ |
| `vrp_hist` | By year, with n | The name's own measured premium (1.1) | Context | Context | Context |
| `next_earnings` | Date, time, status, grade | Event calendar | ✓ | ✓ | ✓ |
| `assignment_risk` | Flag + dividend amount | Ex-dividend inside the option's life | – | ✓ | ✓ |
| `qualified_call` | Pass/fail + reasons | 26 USC 1092 check, per overlay | Shown | ✓ | ✓ |
| `overlay_lot_warning` | Lot list | Assignment would deliver lots under 1 year | ✓ | ✓ | ✓ |
| `regime_v0` | Weak / sideways / up | Interim regime, provisional | Context | ✓ | ✓ |

**Example record:** `{ticker:"AAPL", module_id:"M12", signal:"cc_window", value:"blocked_earnings", timeframe:"ST", evidence_grade:"A", source_ref:"Apple IR notice: earnings 2026-11-02", method:"m12-window-v1", as_of:"2026-10-08"}`

**Timeframe parameters (for the module doc)**

| Parameter | MY | PT | ST (overlay default) |
|---|---|---|---|
| Visibility (D10) | Shown | Shown | Shown |
| Weight in confluence | Low (informational) | Medium | Primary |
| DTE | — | 31–45 (5.1) | 31–45 (5.1) |
| Delta | — | About 15, index-derived | About 15, index-derived |
| Thesis block | Accumulate or add zone blocks | Same | Same |

## Build parts (proposal)
**How each part runs:**
- One conversation each at Medium effort; High only if a design question arises.
- Branches `m12-part1`, `m12-part2`, and so on.
- M12_OPTIONS.md (and DATA_SOURCES.md where relevant) updated in the same commit as the code.
- Fixture tests only.

**Live checks:**
- You run one combined check per part, piping output and errors to a text file and sending it back.
- Claude cannot call the vendors or read `data\`.

**Dependencies:** no new packages expected; the binomial model and bisection are plain Python.

| Part | Contents | Depends on | Live check (one per part) |
|---|---|---|---|
| 1 FRED client and options probe | Shared FRED client (VIX, VXN, VXAPL, VXAZN, VXGOG, DTB3/DGS1MO) (S2.1); realized volatility from bars; `scripts/probe_options.py` (S2.4); DS5 rows; close Q5 | — (M01 shares the client) | Probe: the 5 FRED series; AAPL on one date from Massive Basic (about 5 calls) against VXAPL; reference endpoint; INFQ and ETV listings; one Alpha Vantage calendar call and one Finnhub call. Minutes. |
| 2 Event calendar | `m12_event`; IR notice parser with your confirmation of the first 10 hits; weekly Alpha Vantage pull; cadence estimates from Item 2.02 events; ex-dividend dates from `div_cash` history and declarations; `m12_date_conflict` (4.1–4.3) | 1; M02 7a | One calendar pull plus the parser over stored IR items; report of the next date per name with status |
| 3 Own IV snapshot | `options/snapshot.py`; binomial IV; `iv_obs` and `iv30`; `massive` lane budget; logon catch-up; backfill per 2.2 | 1 | One day's snapshot for AAPL, AMZN, GOOG (method gap against Cboe), TSLA and SPCX: about 25 calls, about 5 minutes |
| 4 IV metrics | Rank, percentile, provisional/insufficient; `iv_rv_gap`; ex-event exclusion (3.2); `iv_event_share`; `vrp_hist`; 1-year and 3-year percentiles | 2, 3 | Printout over the real DB, no network |
| 5 Window, template and signals | `regime_v0` (5.2); `cc_window` with states, hysteresis and reasons; template (5.1); `signal` rows; M12 panel in the UI | 2, 4; M01 trend; M04 gate and M11 thesis when built | Window printout for the watchlist from the real DB; UI checked on scratch data (port 8799) |
| 6 Overlay ledger and tax panel | `overlay_position`, `overlay_lot_link` (plus lots if M01 has not built them); qualified-call checks; FIFO and specific-ID (6.1); forgone upside (6.2); Pub 550 read (6.3) | 5 | You record one overlay on the real DB; panel printout sent back |

## Known gaps
**Not verified (search budget ran out):**
- Whether INFQ and ETV have listed options.
- Free access to Finnhub's earnings calendar and option chain.
- Free access to Alpha Vantage `EARNINGS_CALENDAR`.
- Basic-plan access to Massive's contract-reference endpoint.
- FRED's access route (API key or CSV) and its storage terms; the Cboe reprint notice applies.
- Massive Basic's "Individual" terms for storing data.

**Not read:**
- The Pub 550 body text (qualified covered calls, wash sales).
- The Schwab ex-dividend page (put-against-dividend check).
- Carr & Wu's results beyond the abstract.
- Bakshi & Kapadia's single-stock paper (J. Derivatives 2003).
- The Hemler & Miller paper body.
- Patell & Wolfson (1979), on the pre-earnings IV rise.
- Do, Foster & Gray (2016), known only second-hand.

**Missing evidence or data:**
- No peer-reviewed evidence was found that a regime filter helps single-stock covered calls; the rule stays the owner's (R20).
- No structured free source for upcoming ex-dividend dates.
- Volatility skew is not modelled, so strikes are approximate.
- SPCX cannot have a 1-year IV history before about June 2027.

**Outside M12:**
- Lot and overlay tables are not in code. M01 lot entry is not built.
- M09, M10 and M11 are not designed, so `regime_v0` and the add-trigger stand-in are used meanwhile.

**To check at build:**
- Apple's 2025-10-30 earnings date, against the stored `event` table.
- AAPL's 340.42 close, against the stored Tiingo bar.

## New sources
Provisional IDs. They get S-numbers when added to SOURCES.md. Existing IDs used: S01, S26, S28, S29, S30, S31, S68, S70.

- **S-new-M12-1** Carr, P. & Wu, L. (2009). "Variance Risk Premiums." *Review of Financial Studies* 22(3), 1311–1341. PR. https://ideas.repec.org/a/oup/rfinst/v22y2009i3p1311-1341..html
- **S-new-M12-2** Driessen, J., Maenhout, P. & Vilkov, G. Working paper, July 2013 version (Netspar); same research line as S31. WP. https://www.netspar.nl/wp-content/uploads/061_Driessen.pdf
- **S-new-M12-3** Bakshi, G. & Kapadia, N. (2003). "Delta-Hedged Gains and the Negative Market Volatility Risk Premium." *Review of Financial Studies* 16(2), 527–566. PR. https://ideas.repec.org/a/oup/rfinst/v16y2003i2p527-566.html
- **S-new-M12-4** Cao, J. & Han, B. (2013). "Cross Section of Option Returns and Idiosyncratic Stock Volatility." *Journal of Financial Economics* 108(1), 231–249. PR. https://ideas.repec.org/a/eee/jfinec/v108y2013i1p231-249.html
- **S-new-M12-5** Goyal, A. & Saretto, A. (2009). "Cross-Section of Option Returns and Volatility." *Journal of Financial Economics* 94(2). PR. https://doi.org/10.1016/j.jfineco.2009.01.001
- **S-new-M12-6** Gao, C., Xing, Y. & Zhang, X. (2018). "Anticipating Uncertainty: Straddles around Earnings Announcements." *Journal of Financial and Quantitative Analysis* 53(6), 2587–2617. PR. https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/anticipating-uncertainty-straddles-around-earnings-announcements/7B34877AD5E06304BA3C55FBA3219FDD
- **S-new-M12-7** Dubinsky, A., Johannes, M., Kaeck, A. & Seeger, N. (2019). "Option Pricing of Earnings Announcement Risks." *Review of Financial Studies* 32(2), 646–687. PR. https://ideas.repec.org/a/oup/rfinst/v32y2019i2p646-687..html
- **S-new-M12-8** Pool, V., Stoll, H. & Whaley, R. (2008). *Journal of Financial Markets* 11(1), 1–35, on call holders failing to exercise. PR, bibliographic only. https://ideas.repec.org/a/eee/finmar/v11y2008i1p1-35.html
- **S-new-M12-9** FRED, Cboe volatility series VXAPLCLS, VXAZNCLS, VXGOGCLS, VIXCLS, VXNCLS; Cboe reprint notice. Primary. https://fred.stlouisfed.org/series/VXAPLCLS · https://fred.stlouisfed.org/series/VXAZNCLS · https://fred.stlouisfed.org/series/VXGOGCLS · https://fred.stlouisfed.org/series/VIXCLS
- **S-new-M12-10** Alpha Vantage API documentation: options functions (premium); EARNINGS_CALENDAR. Primary. https://www.alphavantage.co/documentation/
- **S-new-M12-11** Massive (formerly Polygon): options pricing plans; daily ticker summary; option chain snapshot. Primary. https://massive.com/pricing?product=options · https://massive.com/docs/rest/options/aggregates/daily-ticker-summary · https://massive.com/docs/rest/options/snapshots/option-chain-snapshot
- **S-new-M12-12** Alpaca option data docs. Primary. https://docs.alpaca.markets/reference/optionchain · https://docs.alpaca.markets/docs/historical-option-data
- **S-new-M12-13** Tradier market-data docs. Primary. https://docs.tradier.com/docs/market-data
- **S-new-M12-14** Cboe website terms of use (updated 2022-11-16). Primary. https://www.cboe.com/terms
- **S-new-M12-15** 26 U.S. Code § 1092 (straddles; qualified covered calls). Primary. https://www.law.cornell.edu/uscode/text/26/1092 · IRS Publication 550. Primary. https://www.irs.gov/publications/p550
- **S-new-M12-16** Fidelity, "Dividends, options and assignment risk". Other. https://fidelity.com/learning-center/investment-products/options/dividends-options-assignment-risk · Schwab, "Ex-dividend dates: understanding dividend risk" (not read). https://www.schwab.com/learn/story/ex-dividend-dates-understanding-dividend-risk
- **S-new-M12-17** tastylive, "IV Rank & IV Percentile" definitions. Other. https://www.tastylive.com/definitions/iv-rank-iv-percentile
- **S-new-M12-18** Apple earnings dates: iClarified on the Q4 FY26 date (Other) https://www.iclarified.com/102636/apple-to-announce-q4-fy26-earnings-on-november-2 · Apple Newsroom Q2 FY26 results (Primary) https://www.apple.com/newsroom/2026/04/apple-reports-second-quarter-results/ · Apple Q1 FY26 release via Nasdaq (Primary) https://www.nasdaq.com/press-release/apple-reports-first-quarter-results-2026-01-29
- **S-new-M12-19** Saxo, "SpaceX earnings: pricing a first print with no history", 2026-07-30 (quotes from 2026-07-29). Other. https://www.home.saxo/content/articles/options/spacex-earnings-pricing-a-first-print-with-no-history-30072026
- **S-new-M12-20** Bloomberg Law, "SpaceX options to begin trading on Tuesday after IPO". Other. https://news.bgov.com/securities-law/spacex-options-to-begin-trading-on-tuesday-after-ipo
- **S-new-M12-21** AAPL close 2026-10-08 = 340.42. A one-off check against a public chart feed that is rejected for engine use (S70); replace with the stored Tiingo bar at build.
- **S-new-M12-22** Hemler, M. & Miller, T. (2015), OIC-funded study of five options strategies on ten stocks, 2003–13; OCC press release 2015-05-08. Other. https://www.theocc.com/newsroom/press-releases/2015/05-08-new-academic-research-finds-options-based-in
  (This URL was cut off when the pack was written; look it up again at review.)
