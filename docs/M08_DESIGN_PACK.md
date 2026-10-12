# M08 — Design review pack (draft for the owner)

**Status:** research only — nothing is decided until the owner answers (D7); 2026-10-12 · **Effort:** High for this review; each build part Medium. Outputs are research signals, not financial advice.

## How this review runs
- **Order.** One round per section, in the order below. Each round's answers are recorded before the next round starts.
- **What each round contains:**
  - What the research says.
  - A worked example. Figures are real and sourced; invented rows are marked *illustrative*.
  - All cases the rule must handle.
  - Suggestions, numbered S1.1, S1.2 and so on.
  - Failure-mode rows for the M08 doc (D9).
  - Questions, each with lettered options. The recommended option comes first, with one line of why.
- **How to answer.** Plain text, e.g. "1.1a 1.2a 1.3a".
  - Strike any suggestion you reject by number ("S2.3 no"), or reply "rest ok".
  - Answers become D-M08-1 onward.
  - Every threshold is a starting value, tuned by backtest (Round 6).
- **Citations:**
  - S-numbers come from SOURCES.md.
  - S-new-n are M04 pack IDs (pending).
  - S-new-M08-n are provisional and listed under "New sources".
  - [peer-reviewed], [primary] or [other] gives the kind of source.
  - "Abstract checked" means the publisher abstract or a mirror was read on 2026-10-12.
  - "Not re-read" means the claim rests on the known abstract, with the DOI confirmed via Crossref.
- **M04 references.** They point to the M04 design pack draft, which the owner has not answered yet. If M04's answers change, the affected M08 rows change with them.

## Purpose and dependencies
**Purpose.** For every equity in every timeframe, M08 answers two questions:
- How expensive is it against its own history, its peers and an absolute yardstick, using the measure that fits its business stage?
- What do analysts, short sellers, options traders and the press expect of it now?

**Approved revisions it must honour**
- **R6:** PEG only when EPS > 0 and growth > 0; a sales-based fallback; flag cyclicals (S18).
- **R15:** use analyst revisions and dispersion, not price-target levels. Only 38% of targets are met at the horizon (S11).
- **Core decisions:**
  - D10: every output is visible everywhere; stage and profile change weights only.
  - D13: signal record. D14: evidence grades.
  - D8: ambiguous items go to the review queue. D9: failure modes.
  - D16: exits are warnings only.
  - D21: LLM output only with verified quotes.
  - S1: crypto is out of scope, which matters for MSTR. S2: free sources only.
- **M01:** analysts weigh low in MY. Rule 4 raises an exit warning when an owner-set valuation ceiling is hit.
- **D-M02-12:** the PC is never on overnight, so every fetch runs as a background logon catch-up.

**Depends on**

| Module | What M08 uses | Status |
|---|---|---|
| M00 | `fact` with `filed` dates (point-in-time); `price_bar` raw `close`, `adj_close`, `div_cash`, `split_factor` (Tiingo, internal use only, S68; migration 0012); D13 `signal` table | Built. Nothing writes `signal` yet; M04 part 1 adds the writer |
| M01 | Profiles and weights; rule 4 ceiling | Approved |
| M02 | `news_item`, `news_company`, `news_source` (D-M02-58); R19 guidance ledger (`src/engine/guidance/changes.py`); theme crowding (D-M02-57); Alpha Vantage client and its 25/day budget (D-M02-6) | Built |
| M04 | `facts_as_of` (part 1); `lifecycle_stage` (part 2, S5.1); `peer_group` (part 2, D19); survival gate (part 4); dilution and convertibles (part 5); `cvd_state`, normalized earnings and the overreaction gauge (part 8, S6.6) | Pack draft |
| M12 | Options data (DS5, Q5), shared with Round 5 | Not started |
| M10 | Market-level sentiment (VIX, aggregate short interest, S-new-M08-27) stays there | Not started |

---

## Round 1 — Valuation measures by business stage

### What the research says
1. **Forward earnings price best** (S-new-M08-1) [peer-reviewed].
   - The ranking: forward earnings first, then historical earnings. Cash flow and book value tie for third, and sales come last.
   - It holds across almost all industries.
   - The sample needed positive values and analyst forecasts, so it says little about loss-makers.
2. **Low P/E and value.** Low-P/E stocks earned higher risk-adjusted returns (S-new-M08-2, not re-read). Value strategies outperform over multi-year horizons (S35).
3. **Enterprise multiple.** The enterprise multiple "is a strong determinant of stock returns". An EM factor earns 5.28% a year, which the authors read as a discount-rate proxy (S-new-M08-3, abstract checked).
4. **Sales-to-price (R6's sales fallback).** Sales-to-price and debt-to-equity explained 1979–91 returns better than book-to-market and size (S-new-M08-4, abstract checked via a mirror).
   - Caveat: this is an old US sample.
   - A UK test (FAJ 2001) found that S/P does not fully absorb B/M and size.
5. **Internet firms, 1998–99** (S-new-M08-5, abstract checked via a mirror). Weak, bubble-era support for EV/gross profit and M04's `unit_metric` at introduction-stage firms.
   - Net income had no significant link to price.
   - Gross profit did, and usage measures usually added explanatory power.
   - Keating's discussion criticised the method.
6. **Life-cycle stage.** Dickinson classifies stage from cash-flow signs (M04 S-new-56). M04 part 2 builds `lifecycle_stage`, and M08 reuses it.
7. **Peer quality.** The peer classification scheme changes how well peers explain multiples (M04 S-new-2), so peer percentiles inherit M04's peer quality (D19).

**Data**
- **Stored** (`src/engine/sec/xbrl_facts.py` CONCEPTS): revenue, gross_profit, operating_income, net_income, eps_diluted, da, operating_cash_flow, capex, cash, short_term_investments, long_term_debt, equity, shares_outstanding, rpo. `fact.filed` allows as-of valuation without look-ahead.
- **Debt tag.** `long_term_debt` maps to `LongTermDebtNoncurrent` or `LongTermDebtAndCapitalLeaseObligations`. The second already includes capital/finance leases for some filers.
- **Missing EV inputs:**
  - current debt (`DebtCurrent`, `LongTermDebtCurrent`);
  - operating-lease liabilities, plus finance leases where the debt tag excludes them;
  - preferred stock;
  - noncontrolling interest.
- **Also missing:** weighted diluted shares and dividends paid. M04 part 1 splits the share concepts, so M08 adds only what M04 does not.
- **Cross-check.** Finnhub `/stock/metric` returns vendor P/E, P/S and so on. It has no premium marker in the spec (S-new-M08-20), so it is free. Grade B; the licence forbids sharing (DS4).
- **Forward multiples** need estimates (Round 3).

### Worked example
Closes: Yahoo chart API (S-new-M08-43, other, re-checked). They will be replaced from `price_bar` at build. SEC figures come from companyconcept, using the pattern in M04 S-new-1.

| Item | INFQ (losses; intro/growth) | NVDA (profitable) |
|---|---|---|
| Close 2026-10-09 | $11.04 | $229.28 |
| Shares | 225,357,052 (dei, 10-Q filed 2026-08-18) | not fetched |
| TTM revenue | $41.081M = FY2025 31,108k − H1 2025 13,472k + H1 2026 23,445k (10-Q accn 0001628280-26-057508) | — |
| TTM diluted EPS | n/m (loss) | $7.91 = 1.30 + 1.76 + 2.39 + 2.46. Q4 FY26 is derived: 4.90 − 0.76 − 1.08 − 1.30 = 1.76. Quick check only; the engine uses TTM net income ÷ latest diluted shares |
| Result | Market cap $2.488B; P/S 60.6×; EV missing (cash and debt not fetched, so not zero) | TTM P/E ≈ 29.0× |

Sources:
- https://data.sec.gov/api/xbrl/companyconcept/CIK0002007825/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json
- https://data.sec.gov/api/xbrl/companyconcept/CIK0001045810/us-gaap/EarningsPerShareDiluted.json

At build, confirm that INFQ's FY2025 revenue comes from the same recast series as the H1 figures (case 9).

### All cases
1. **Profitable, long history, ≥ 5 SEC peers** (NVDA, MSFT): all measures and both percentiles.
2. **Revenue but losses** (INFQ): P/E and EV/EBIT are n/m. EV/S, EV/GP and P/S lead.
3. **Gross profit ≤ 0:** EV/GP is n/m too. Show EV/S plus runway.
4. **Any denominator ≤ 0:** no value, reason `not_meaningful`.
5. **Negative equity:** P/B is n/m.
6. **Net cash above market cap (EV ≤ 0):** EV multiples are n/m.
7. **EV component missing, or the debt tag's lease coverage unknown:** market-cap measures, labelled "EV incomplete".
8. **Short own history:** own-history percentile missing below 20 quarterly points.
   - SPCX has been listed only since 2026-06-12, so it has no own percentile for about 5 years.
   - INFQ is in the same position.
9. **SPAC successor or recast series** (INFQ): one series per TTM, with the break flagged.
   - INFQ's FY2025 `NetIncomeLoss` is −66,931,068 in the 10-K filed 2026-03-31.
   - It is −32,228,000 in the 10-Q filed 2026-08-18 for the same period (not re-checked).
10. **20-F/IFRS filer with quarters in 6-K** (GFS): probably annual multiples only.
11. **Holding company valued on a crypto asset** (MSTR; fair value under ASU 2023-08, S-new-M08-42): see Q1.3.
12. **< 5 peers, or key peers outside the SEC** (SK hynix): own history only.
13. **Stage missing or unstable:**
    - M04 part 2 not built: all measures, no headline (`stage_missing`).
    - Stage flips on a one-off: M04's review path.
14. **Split between the share-count date and d:** shares adjusted by `split_factor`.
15. **No price on d** (holiday, before listing): use the last close on or before d. If there is none, the value is missing.
16. **Owner valuation ceiling hit** (M01 rule 4): exit warning.

### Suggestions
- **S1.1** Compute every measure for every company and show them all (D10). The stage only picks the headline and its weight. The cyclical flag (Round 2) overrides the stage.

| Stage (M04) | Headline | Shown next to it |
|---|---|---|
| Introduction | EV/sales, EV/gross profit | M04 runway, `unit_metric` |
| Growth | EV/sales, EV/gross profit | forward P/E; PEG when R6 passes |
| Mature | forward and TTM P/E, EV/EBIT | FCF yield |
| Shake-out | EV/EBIT on normalized earnings | — |
| Decline | EV/EBIT, P/B, FCF yield | survival gate |

- **S1.2** Use three frames:
  - own-history percentile;
  - peer percentile;
  - absolute earnings yield, shown beside the 10-year Treasury yield (FRED DGS10, S-new-M08-45).
- **S1.3** As-of rule for date d: raw `close` at d × shares last filed on or before d (adjusted by any `split_factor` since) ÷ fundamentals filed on or before d, via M04 `facts_as_of`.
- **S1.4** Grade-A signals:
  - `valuation_headline` {value, method, e.g. "EV/S TTM; stage=intro"};
  - `valuation_pctile_own`;
  - `valuation_pctile_peer`;
  - `valuation_reason` when no value is computed.
- **S1.5** One migration adds:
  - debt_current;
  - lease liabilities, with a flag for whether the debt tag already includes leases;
  - preferred stock;
  - noncontrolling interest;
  - diluted weighted shares, unless M04 part 1 adds them;
  - dividends paid.

  MSTR's digital-asset tag is added after a probe.
- **S1.6** Valuation ceiling (M01 rule 4): the owner sets it per position, in the headline measure. M08 raises the exit warning (D16).

### Failure modes
| Indicator | How it misleads | Guard |
|---|---|---|
| P/E, EV/EBIT | A negative or near-zero denominator gives a meaningless number | Denominator ≤ 0 → no value plus a reason code (`not_meaningful`, as in D-SRCH-15) |
| TTM EPS summed from quarters | Share counts change; Q4 is not reported separately | TTM net income ÷ latest diluted shares; Q4 = FY − 9M (M00_SEC_DATA facts note) |
| EV | Missing debt or leases understate EV; a lease-inclusive debt tag plus lease liabilities double-counts | EV only when every component is present and the tag's lease coverage is known; else market cap labelled "EV incomplete" |
| Market cap at a past date | `adj_close` is dividend- and split-adjusted; as-filed shares predate splits | Raw `close` × split-adjusted as-filed shares |
| Own-history percentile | Short history (SPCX, INFQ) or structural change | ≥ 20 quarterly points, else missing |
| Peer percentile | Wrong peers; peers outside the SEC (SK hynix) | M04 owner-curated peers; < 5 peers → own history only |
| Stage label | Cash-flow signs flip around one-offs | M04's stage and its review queue |
| P/S for loss-makers | Ignores the path to profit | Shown with M04 runway and the survival gate |
| TTM across a SPAC or recast break | Mixes predecessor and successor | One series per TTM; break flagged |

### Questions
- **1.1 Headline measure per stage.**
  - a) The engine proposes from M04 `lifecycle_stage`; the owner overrides per company.
  - b) The owner sets every company.
  - c) One fixed set for all companies.
  - Why (a): it reuses M04's stage and review path, so the owner acts only on exceptions.
- **1.2 Scoring frame.**
  - a) Show both percentiles. Score on the peer percentile with ≥ 5 peers, else on own history.
  - b) Own history only.
  - c) Absolute thresholds.
  - Why (a): peers are the sharper comparison where they exist (S-new-M08-1, M04 S-new-2), and own history covers the rest.
- **1.3 MSTR.**
  - a) Holding-company headline: market cap ÷ bitcoin holdings at fair value (mNAV), labelled as crypto exposure (S1).
  - b) Treat it as an ordinary software company.
  - c) Leave it out of M08 valuation.
  - Why (a): its value and its EPS move with bitcoin (ASU 2023-08), not with software earnings.

---

## Round 2 — PEG (R6), the sales fallback and the cyclical flag

### What the research says
1. **PEG works only as a rough ranking** (S-new-M08-6, abstract checked via a mirror).
   - PEG assumes the short-run growth forecast also holds for the long run.
   - Its expected-return estimates are biased downward, but they correlate highly with refined estimates.
2. **Analysts use PEG-type heuristics.** Their recommendations follow PEG and long-term-growth heuristics rather than residual-income values (S-new-M08-7, not re-read).
3. **P/E differences persist** (S-new-M08-8, abstract checked via a search summary).
   - Initial P/E differences between portfolios persist for up to 14 years.
   - Growth and risk explain little of that.
   - P/E relates negatively to same-year growth and positively to next-year growth, which fits short-lived earnings distortions.
   - The authors attribute the long persistence mainly to accounting-method differences.
4. **P/E tracks current ROE** and is a poor signal of future growth (S-new-M08-9, CFA digest checked).
   - P/B is the better indicator of future ROE and growth.
   - The "Molodovsky effect": earnings reverse after unusually high or low years.
5. **Mean reversion and averaging.** Profitability mean-reverts (M04 S-new-55), which supports normalized earnings for cyclicals. Multi-year averaging (CAPE) has its own accounting distortions (M04 S-new-67).
6. **Known PEG traps** (S18): negative earnings, and the cyclical PEG trap.

**Data**
- EPS, revenue and operating income are stored with 10+ years of history, after the tag switches noted in the M04 pack (e.g. Micron's `SalesRevenueNet`).
- Forward growth comes from Alpha Vantage `EARNINGS_ESTIMATES` (Round 3).
- M04 normalized earnings and `cvd_state` arrive with M04 part 8.
  - M04 S6.6 shows normalized earnings only when `cvd_state` is CYCLICAL_TROUGH or AMBIGUOUS.
  - M08's cyclical mode therefore needs that rule widened, or its own computation (Q2.4).

### Worked example
Micron, at each 10-K filing date. EPS, revenue and operating income from SEC companyconcept. Closes from Yahoo (other, re-checked).

| 10-K filed | Close | FY diluted EPS | Trailing P/E | Next FY EPS | Price a year later |
|---|---|---|---|---|---|
| 2022-10-07 | $52.91 | 7.75 (FY22) | 6.8× | −5.34 | $69.96 (+32%) |
| 2023-10-06 | $69.96 | −5.34 (FY23) | n/m | 0.70 | $102.25 (+46%) |
| 2024-10-04 | $102.25 | 0.70 (FY24) | 146.1× | 7.59 | $187.83 (+84%) |
| 2025-10-03 | $187.83 | 7.59 (FY25) | 24.7× | — | $1,029.00 (2026-10-09) |

- **PEG on 2024-10-04:** none. EPS is positive, but growth runs from a −5.34 base (`base_nonpositive`), and Micron is cyclical.
- **Normalized P/E on 2024-10-04:** FY2019–24 average EPS is $2.688, giving 38.0×, against 146× trailing.
- **Normalized operating income:**
  - Cycle-average operating margin FY2019–24 = 21,923 ÷ 143,955 = 15.2%, against 5.2% in FY2024.
  - On FY2024 revenue of $25.111B, normalized operating income ≈ $3.82B.
- **Cyclical proposal fires:** the operating margin ran from −37.0% (FY23) to 31.5% (FY22) over FY2019–25.
- **NVDA:** H1 FY27 EPS growth is +164% (4.85 vs 1.84). That gives PEG 0.18 on the approximate trailing P/E, so the reason is `growth_above_cap`.
- **Sources:**
  - https://data.sec.gov/api/xbrl/companyconcept/CIK0000723125/us-gaap/EarningsPerShareDiluted.json
  - the same path for RevenueFromContractWithCustomerExcludingAssessedTax.json and OperatingIncomeLoss.json
  - https://query1.finance.yahoo.com/v8/finance/chart/MU

### All cases
1. **PEG computed:** TTM and forward EPS > 0, 0 < g ≤ cap, not cyclical.
2. **TTM or forward EPS ≤ 0:** `eps_nonpositive`; the sales fallback applies (Q2.1).
3. **g ≤ 0:** `growth_nonpositive`.
4. **Growth from a negative or tiny base** (MU FY2024 from −5.34): `base_nonpositive`.
5. **g above the cap** (NVDA +164%): `growth_above_cap`; show EV/sales.
6. **Cyclical flag set:** `cyclical`; normalized headline.
7. **Earnings driven by fair-value gains** (MSTR, ASU 2023-08): `fair_value_earnings`.
8. **No consensus growth** (coverage not yet probed for INFQ, SPCX, GFS): PEG missing (`growth_missing`, proposed). Trailing CAGR is shown labelled and never substituted.
9. **History under 3 years** (SPCX, INFQ): trailing CAGR missing.
10. **Vendor non-GAAP growth divided into a GAAP P/E:** both bases labelled.
11. **Cyclical at peak with a low P/E** (MU, Oct 2022): trailing P/E carries the warning "inverts at cycle extremes".
12. **CYCLICAL_TROUGH with a high trailing P/E** (MU, Oct 2024): "trough earnings" note, not "expensive".
13. **STRUCTURAL_DECLINE with a low P/E:** value-trap warning.
14. **Engine proposes cyclical on a one-off loss:** review queue; the owner rejects it.
15. **M04 normalized earnings not built, or hidden for this `cvd_state`:** see Q2.4.

### Suggestions
- **S2.1** Compute PEG only when all of these hold:
  - TTM EPS > 0 and forward EPS > 0;
  - 0 < g ≤ cap;
  - the company is not flagged cyclical.

  Otherwise emit no value, plus one reason code: `eps_nonpositive`, `growth_nonpositive`, `base_nonpositive`, `growth_above_cap`, `cyclical`, `fair_value_earnings`, or `growth_missing`.
- **S2.2** Growth basis:
  - Primary: FY2 over FY1 consensus EPS (Alpha Vantage, grade B, labelled).
  - Shown beside it: trailing 3-year EPS CAGR (the M01 window).
- **S2.3** `cyclical_flag`, confirmed by the owner per company:
  - The engine proposes it (D8) when there is at least one EPS sign change in 10 years, or an operating-margin range ≥ 30 pp over the last full cycle.
  - The cyclical headline is normalized P/E (cycle-average EPS) or EV over normalized EBIT (cycle-average margin × current revenue), plus P/B.
- **S2.4** Read the flag together with `cvd_state`:
  - CYCLICAL_TROUGH with a high trailing P/E → "trough earnings" note.
  - STRUCTURAL_DECLINE with a low P/E → value-trap warning.
- **S2.5** Signals: `peg`, `peg_reason`, `cyclical_flag`, `valuation_normalized`.

### Failure modes
| Case | How it misleads | Guard |
|---|---|---|
| Growth from a negative or tiny base | MU FY2024 growth from −5.34 is undefined | `base_nonpositive`; no PEG |
| Extreme growth on a ramp | NVDA +164% gives PEG 0.18 | Growth cap (Q2.3) |
| Analyst growth is optimistic | Walk-down and long-term-growth bias (Round 3) | Label the growth source; show trailing growth beside it |
| Fair-value gains in EPS | MSTR EPS moves with bitcoin | PEG off when M04 flags fair-value-driven earnings |
| Peak-cycle low P/E | MU 6.8× in Oct 2022, then EPS −5.34 | Cyclical mode: normalized headline; trailing P/E carries a warning |
| Trough-cycle high P/E | MU 146× in Oct 2024, then EPS 7.59 | Same; under CYCLICAL_TROUGH this is the expected setup |
| Mixed bases | Vendor non-GAAP growth into a GAAP P/E | Both bases labelled on the PEG |

### Questions
- **2.1 R6 sales-based fallback.**
  - a) EV/sales percentile against own history and peers, with no growth adjustment.
  - b) EV/sales ÷ forward revenue growth. This is a heuristic; no peer-reviewed test was found.
  - c) EV/gross profit.
  - Why (a): it is the only variant with return evidence (S-new-M08-4), and EV/GP is shown anyway.
- **2.2 Normalization for cyclicals.**
  - a) M04 normalized earnings over ≥ 7 years, covering a full cycle.
  - b) A 5-year average EPS.
  - c) A 10-year CAPE-style average.
  - Why (a): Micron's cycle ran FY2019–25 (above), and a 5-year window can miss a trough.
- **2.3 Growth cap for PEG.**
  - a) PEG only when 0 < g ≤ 50%; above that, say "growth too high for PEG" and show EV/sales.
  - b) No cap.
  - c) The owner sets the cap per company.
  - Why (a): PEG treats short-run growth as long-run growth (S-new-M08-6), which fails worst on ramps.
- **2.4 Source of normalized earnings.**
  - a) M08 computes an interim normalized EPS and EBIT now, M04 S6.6 is widened to every cyclical-flagged company, and M08 switches to M04's figures at M04 part 8.
  - b) M08 keeps its own computation permanently.
  - c) Wait for M04 part 8.
  - Why (a): there is one definition in the long run, and M08 is not blocked.

---

## Round 3 — Analyst estimate revisions and dispersion (R15)

### What the research says
1. **Earnings momentum.** Earnings momentum, including forecast revisions, predicts returns over 6–12 months, partly separately from price momentum (S-new-M08-10, not re-read).
2. **Recommendations: changes matter more than levels** (S-new-M08-11).
   - Analysts favour "glamour" stocks.
   - The consensus level adds value only for stocks with favourable quantitative traits.
   - The quarterly change in the consensus recommendation is the robust predictor. This supports `rec_change_3m`, not the estimate signals.
3. **Drift after changes.** Prices drift after recommendation changes, more after downgrades (S-new-M08-12, not re-read).
4. **Costs.** Consensus-recommendation portfolios earn gross abnormal returns, but turnover costs erase them (S-new-M08-13, not re-read).
5. **Dispersion** (S-new-M08-14, S-new-M08-15).
   - Higher forecast dispersion leads to lower future returns, most strongly in small stocks and past losers.
   - The effect is concentrated in poorly rated firms (S-new-M08-15, not re-read).
6. **Walk-down.** Forecasts walk down to beatable levels before announcements (S-new-M08-16, not re-read).
7. **Low coverage.** News travels more slowly where coverage is low (S-new-M08-17). This may matter for INFQ. SPCX's coverage is unverified, and a very large IPO may not have low coverage.
8. **Price targets and decay.**
   - Only 38% of targets are met at the horizon (S11).
   - Anomalies decay after publication (M04 S-new-9, S-new-10), so revisions are a signal, not an edge.
9. **Post-earnings drift** supports a surprise signal (S-new-M08-18).

**Data** (S-new-M08-19, S-new-M08-20)
- **Alpha Vantage `EARNINGS_ESTIMATES`** is not marked Premium (re-checked 2026-10-12). Its fields, from the IBM demo:
  - fiscal-year and fiscal-quarter horizons, past quarters included;
  - EPS average, high, low and analyst count;
  - the average 7, 30, 60 and 90 days ago;
  - revision up and down counts over 7 and 30 days (`revision_down_trailing_7_days` was null in every demo row);
  - revenue average, high, low and count, with no history.
- **Limits:**
  - There is no standard deviation, so dispersion has to be range-based.
  - There is no history beyond 90 days, so weekly snapshots must build the engine's own store.
  - The 25 calls/day are shared with transcripts (D-M02-6). The personal-use terms are already accepted (DS1).
- **Alpha Vantage `EARNINGS`** (not Premium): reported EPS against the estimate, with the surprise.
- **Finnhub:**
  - Free: `/stock/recommendation` (monthly counts), `/stock/earnings` (last 4 quarters), `/calendar/earnings` (1 month).
  - Premium: `/stock/eps-estimate`, `/stock/revenue-estimate`, `/stock/price-target`, `/stock/upgrade-downgrade`.
- **SEC** has no analyst data. The grade-A company-side series is the R19 guidance ledger.

### Worked example
Real data: Alpha Vantage demo response, 2026-10-12. It is IBM because the demo key serves only IBM.

| Horizon | Avg EPS | 90 d ago | Rev. 90 d | Rev. 30 d | Up/down 30 d | Count | Dispersion |
|---|---|---|---|---|---|---|---|
| FY 2027-12-31 | 13.1512 | 13.4736 | −2.39% | −0.09% | 11 / 10 → breadth +0.04 | 23 | (13.86 − 12.3018) ÷ 13.1512 = 11.8% |
| FY 2026-12-31 | 12.3121 | 12.4709 | −1.27% | −0.07% | 0 / 1 | 23 | 4.5% |
| *Illustrative:* MU FY1 | 0.08 | −0.40 | n/m (sign change) | — | — | 2 | not computed (count < 3) |

### All cases
1. **Coverage ≥ 3 with FY1 and FY2:** every signal.
2. **Count < 3:** no dispersion; the count is shown.
3. **No coverage** (possibly INFQ, SPCX, GFS; unprobed): missing, with a low-coverage note.
4. **|avg| < $0.10, or the sign changes in the window:** revision n/m.
5. **Null vendor revision count:** missing, never zero.
6. **Non-calendar fiscal year** (MU Aug, NVDA Jan, MSFT Jun): map by the vendor's period-end `date`.
7. **Within 30 days before the report:** walk-down flag.
8. **Snapshot missed** (budget spent, PC off): missing, and shown in the run report.
9. **Revisions beyond 90 days:** only from the engine's own snapshots, so missing until enough have accumulated.
10. **Guidance moves against estimates** (raised while estimates were cut, or the reverse): review note.
11. **High dispersion:** a warning only together with M04 credit or survival stress; otherwise info.
12. **Earnings reported:** `eps_surprise` on the vendor basis.
13. **Revenue estimates:** level and range only.

### Suggestions
- **S3.1** New table `estimate_snapshot` (ticker, horizon, period_end, every vendor field, fetched_at).
  - Weekly rotation of ≤ 5 calls a day, run in the background (D-M02-12).
- **S3.2** Signals:
  - `est_revision_30d` and `est_revision_90d` (FY1 and FY2 averages);
  - `est_breadth_30d` = (up − down) ÷ count;
  - `est_dispersion` = (high − low) ÷ |avg|;
  - `est_coverage` (the count);
  - `rec_change_3m` (Finnhub mean-score change);
  - `eps_surprise` (Alpha Vantage `EARNINGS`).
- **S3.3** Show the R19 guidance change (grade A) next to estimate revisions (grade B). When they conflict, write a review note (D8).
- **S3.4** Dispersion becomes a warning only with M04 credit or survival stress (S-new-M08-15).

### Failure modes
| Indicator | How it misleads | Guard |
|---|---|---|
| Consensus | Contributor set and basis unknown; usually non-GAAP | Label "vendor basis"; never put it in one ratio with SEC GAAP EPS without the label |
| Revision % | Near-zero or sign-changing base | n/m when \|avg\| < $0.10 or the sign changes |
| Dispersion (range) | One outlier analyst; meaningless when count < 3 | Only when count ≥ 3; show the count |
| Pre-earnings revisions | Walk-down biases them down (S-new-M08-16) | Flag revisions within 30 days of the report |
| Fiscal labels | MU, NVDA and MSFT fiscal years differ | Map by period end (D-M02-6 lesson) |
| Missed snapshot | Budget exhausted | Missing, never zero; shown in the run report |
| Recommendation levels | Glamour bias (S-new-M08-11) | Changes shown; levels secondary |
| Null revision counts | Vendor returns null | Missing, never zero |

### Questions
- **3.1 Estimate source.**
  - a) Alpha Vantage `EARNINGS_ESTIMATES` weekly snapshot, plus Finnhub recommendations and surprises.
  - b) Finnhub only, which gives no estimates.
  - c) Defer until a paid feed (S2).
  - Why (a): it is the only free source of revisions and dispersion, which R15 asks for.
- **3.2 Alpha Vantage budget.**
  - a) ≤ 5 estimate calls a day; transcripts take priority in earnings weeks.
  - b) Estimates first.
  - c) Estimates only on request.
  - Why (a): the call-guidance pipeline (D-M02-6) already depends on the 25/day budget.
- **3.3 Recommendation levels.**
  - a) Show changes; levels on click.
  - b) Show both equally.
  - c) Skip recommendations.
  - Why (a): changes carry the signal and levels carry glamour bias (S-new-M08-11).

---

## Round 4 — Short interest and short-sale volume

### What the research says
1. **Short interest with constraints.** Stocks underperform where high short interest meets short-sale constraints, such as low institutional ownership (S-new-M08-21, not re-read).
2. **Short-sale flow, not short interest** (S-new-M08-22, abstract checked via a mirror).
   - The paper uses daily NYSE order data from 2000–04.
   - Heavily shorted stocks underperform lightly shorted ones by a risk-adjusted 1.16% over 20 trading days.
   - Institutional non-program shorts are the most informative.
   - This bears on short volume, not FINRA short interest. FINRA's off-exchange files are a different measure again.
3. **Days to cover.** DTC predicts poor returns better than the short ratio; a long-short DTC strategy earns 1.2% a month (S-new-M08-23, working paper, abstract checked).
4. **Daily short sellers** short more after price rises and predict short-horizon declines (S-new-M08-24, not re-read).
5. **Convertible arbitrage.** Short interest rises after convertible issues (1993–2006). This is arbitrage hedging, not a bearish view, and it applies directly to MSTR (S-new-M08-25, abstract checked via a mirror).
6. **Small float.** Small float and lockup expirations go with speculative prices (S-new-M08-26, not re-read). This is relevant to SPCX and INFQ.
7. **Aggregate short interest** predicts market returns (S-new-M08-27). This belongs to M10.
8. **FINRA Rule 4560 short interest** (S-new-M08-28):
   - reported twice a month, at the 15th and month-end settlement dates;
   - published on the 7th business day after settlement;
   - covers all exchange-listed and OTC equities;
   - up to 5 rolling years in the grid and API.
9. **FINRA daily short-volume files** (S-new-M08-28):
   - free, no key;
   - posted by 6 pm ET the same day; consolidated from 2018-08-01;
   - cover off-exchange (TRF, ADF, ORF) trades only.

**Data**
- **Massive short interest** (S-new-M08-29): sourced from FINRA, with `short_interest`, `avg_daily_volume`, `days_to_cover` and `settlement_date` from 2017-12-29.
  - The docs say "Included in all Stocks plans", with 2 years on Basic.
  - The pricing page's Basic list does not mention it, so a probe is needed. The key exists; the limit is 5 calls/min.
- **FINRA API:** needs a free Individual account ("not intended for commercial purposes at this time"); 1,200 requests/min per IP.
- **Nasdaq quote API:** undocumented, used for the example only (S-new-M08-30). It rejected INFQ.
- **Denominator:** `shares_outstanding` as of the settlement date.
  - The M04 pack found that MSTR has neither non-dimensional shares tag, so M04 part 1's cover counts are needed.
- **Rule 13f-2 / Form SHO:** not verified; the SEC pages returned 404.

### Worked example
MSTR short interest from the Nasdaq API (other), retrieved 2026-10-12.

| Settlement | Short interest | Avg daily volume | DTC |
|---|---|---|---|
| 2026-06-30 | 42,776,693 | 32,519,811 | 1.32 |
| 2026-07-31 | 32,480,941 | 15,066,603 | 2.16 |
| 2026-08-31 | 32,622,124 | 32,853,234 | 1.00 (0.99 computed) |
| 2026-09-30 | 29,376,814 | 23,816,526 | 1.23 |

- Short interest is down 31% since June.
- Strategy has convertible notes outstanding (S-new-M08-44), so part of this may be hedging (S-new-M08-25).
- % of shares is missing because shares were not fetched.

FINRA consolidated short-volume file for 2026-10-09 (S-new-M08-41): short volume as a share of off-exchange volume.

| Ticker | Share | Ticker | Share | Ticker | Share |
|---|---|---|---|---|---|
| INFQ | 64.4% | NVDA | 48.2% | MRVL | 38.3% |
| AAPL | 58.9% | TSLA | 45.4% | MU | 37.8% |
| SPCX | 58.0% | GFS | 44.6% | MSFT | 36.5% |
| META | 44.4% | MSTR | 42.3% | INTC | 36.0% |
| BA | 39.8% | GOOG | 33.7% | AMZN | 29.2% |

AAPL's 58.9% shows why this is not short interest.

### All cases
1. **Normal case:** short interest and as-of shares known → every signal.
2. **Convertibles outstanding** (MSTR, from M04 part 5): "may be hedging" label.
3. **Issuance changes the denominator** (MSTR at-the-market issuance): as-of shares plus an M04 dilution note.
4. **Shares tag missing** (MSTR): % missing; DTC is still computed.
5. **Volume spike shrinks DTC** (MSTR 2026-08-31): show both inputs and use the own percentile.
6. **New listing with a small float or lockup** (SPCX, INFQ): info flag.
7. **Publication lag:** show the settlement date and the data's age.
8. **History under 2 years:** `si_pctile_own` missing.
9. **High short interest alone:** never a buy signal; squeeze info for ST only.
10. **Top-decile, rising, with an M04 earnings-quality or dilution flag:** warning.
11. **Short-volume share:** context only.
12. **Massive Basic has no access:** FINRA API fallback.

### Suggestions
- **S4.1** Twice-monthly `short_interest` table (ticker, settlement_date, si, adv, dtc, source, fetched_at).
  - Source: Massive, with the FINRA API as fallback.
  - Run after FINRA's publication day.
- **S4.2** Signals: `si_pct_shares`, `dtc` (computed from the inputs), `si_change_3m` (over 6 settlements), `si_pctile_own` (2 years).
  - A warning fires when all three hold: own top decile, rising, and an M04 flag.
- **S4.3** Store the daily short-volume files for context, with weight 0 until a backtest.

### Failure modes
| Indicator | How it misleads | Guard |
|---|---|---|
| Short interest | 2–3 weeks stale at publication | Show settlement date and age |
| High short interest | Hedges: convertible arbitrage (MSTR), market makers, ETF arbitrage | "May be hedging" label when M04 part 5 finds convertibles |
| High short interest | Could be bearish information or squeeze fuel | Never a buy signal alone; squeeze info for ST only |
| Days to cover | Volume spikes shrink it | Own-history percentile; show both inputs; compute DTC from the inputs |
| Short-volume share | Includes market-maker shorting; off-exchange denominator only | Context only |
| % of shares | Issuance changes the denominator | As-of shares; M04 dilution note |
| New listings | Small float, lockups | Float and lockup info flag |

### Questions
- **4.1 Source.**
  - a) Massive (probe Basic access first), with the FINRA API as fallback.
  - b) FINRA API only (the owner creates a free account).
  - c) Skip short interest.
  - Why (a): the key already exists and DTC comes ready-made; FINRA covers any gap.
- **4.2 Daily short volume.**
  - a) Store as context, with no weight.
  - b) Signal on an own-history z-score.
  - c) Do not collect.
  - Why (a): the evidence (S-new-M08-22) uses NYSE order data, not FINRA's off-exchange files.
- **4.3 Evidence grade for FINRA short interest.**
  - a) A.
  - b) B.
  - Why (a): it is a regulatory compilation of broker reports under Rule 4560.

---

## Round 5 — Options-implied sentiment (skew, IV)

### What the research says
1. **Steep smirks underperform** (S-new-M08-31, abstract checked).
   - Steepest-smirk stocks underperform the flattest by 10.9% a year, risk-adjusted.
   - The effect "persists for at least 6 months".
   - Steep-smirk firms have the worst earnings shocks the next quarter.
2. **Expensive calls beat expensive puts** by 50 bp a week, but "the degree of predictability decreases over the sample period" (S-new-M08-32, abstract checked).
3. **Call-put IV spreads** predict returns (S-new-M08-33, not re-read).
4. **IV changes.** Rising call IV predicts higher returns and rising put IV lower returns (S-new-M08-34, not re-read).
5. **Free availability** (S-new-M08-19, S-new-M08-29):
   - Alpha Vantage options endpoints are Premium.
   - Massive's chain snapshot (IV, greeks, open interest) excludes Options Basic.
   - Options Basic does include per-contract daily OHLC with 2 years of history.
   - Finnhub has no chain endpoint.
   - This is DS5 / Q5, shared with M12.

**Data**
- The only free route is to compute IV with an American binomial model from:
  - Massive Basic daily closes;
  - the Tiingo underlying close;
  - a FRED short rate.
- About 3 contracts × 16 tickers ≈ 48 calls a day, at 5/min ≈ 10 minutes in the background. This competes with the Massive news backup.
- Contract selection needs Massive's contracts reference endpoint; its plan was not checked.
- There is no IV history until the engine's own snapshots accumulate.

### Worked example (illustrative; invented numbers)
MU at a 30-day expiry:
- ATM call IV 52%, ATM put IV 53%, 0.9-moneyness put IV 61%.
- `smirk` = 61 − 52 = 9 pp; `cp_spread` = −1 pp.
- The smirk's own 2-year percentile is the 85th, so ST info shows "steep smirk".
- If that put traded 0 contracts that day, the smirk is not computed (missing).

### All cases
1. **Liquid contracts traded that day:** compute.
2. **A contract not traded that day:** missing.
3. **Illiquid OTM puts** (INFQ, SPCX): minimum-volume rule, else missing.
4. **Earnings inside expiry:** pick another expiry, or flag it (M12 rule).
5. **Dividend payer, early exercise:** American binomial with Tiingo `div_cash`.
6. **No own IV history yet:** percentile missing.
7. **No listed options:** missing.
8. **Massive budget used by the news backup:** skip the day; missing.

### Suggestions
- **S5.1** Decide DS5 with M12 (Q5). M08 defines the data contract now and builds options signals only after that decision.
- **S5.2** If computing is approved, take daily per ticker, at the expiry nearest 30 days that avoids earnings: ATM call, ATM put, and the put nearest 0.9 moneyness.
  - `smirk` = IV(OTM put) − IV(ATM call) (S-new-M08-31).
  - `cp_spread` = IV(ATM call) − IV(ATM put), a proxy for S-new-M08-32.
  - `iv_change_1m`.
- **S5.3** Weight in ST and PT only; MY shows it for information (D10).

### Failure modes
| Issue | Effect | Guard |
|---|---|---|
| Option last trades are not synchronous with the underlying close | Spurious skew | Only contracts traded that day; store volume |
| Illiquid OTM puts | No meaningful smirk | Minimum-volume rule, else missing |
| Earnings inside expiry | IV and skew inflated | Choose another expiry or flag it |
| Early exercise, dividends | European-model IV is biased | American binomial with dividends |
| Hedging demand | Puts bought for insurance, not information | Low weight; ST/PT only |
| Decay | Weaker in later samples (S-new-M08-32) | Backtest before weighting |

### Questions
- **5.1 Options data.**
  - a) Defer until Q5 is decided with M12.
  - b) Compute IV from Massive Basic closes now.
  - c) Wait for a paid plan (S2).
  - Why (a): M12 needs the same data, so one decision serves both modules.
- **5.2 If computing.**
  - a) Watchlist only, 3 contracts per ticker per day.
  - b) The full chain weekly.
  - Why (a): it fits the 5/min budget in about 10 background minutes.

---

## Round 6 — News tone and attention; assembling the signals per timeframe

### What the research says
1. **Media pessimism.** High media pessimism predicts downward price pressure, then reversion (S-new-M08-35, not re-read).
2. **Negative words in firm news** predict low earnings, and prices briefly underreact (S-new-M08-36, not re-read).
3. **Finance-specific word lists** (S-new-M08-37).
   - General negative lists misclassify financial text, so the paper introduced finance-specific lists.
   - The dictionary is "free for use in academic research", and commercial licences come through the authors. Personal, non-academic use is not clearly covered.
4. **Recessions.** Tone predictability is concentrated in recessions (S-new-M08-38, not re-read).
5. **Horizons** (S-new-M08-39, abstract checked via a mirror; proprietary sentiment score).
   - Daily news predicts returns for 1–2 days; weekly news for about a quarter.
   - Negative news has a slower, longer reaction, much of it around the next earnings.
6. **LLM headline scores.** GPT-4 headline scores predict initial reactions and "significantly predict the subsequent drift", especially for small stocks and negative news (S-new-M08-40, working paper, abstract checked).
7. **Attention.** Attention drives individual buying (S91). M02 theme crowding (D-M02-57) already covers the theme level.
8. **Vendor tone is not free.** Finnhub news and social sentiment and Alpha Vantage `NEWS_SENTIMENT` are all Premium (S-new-M08-19, S-new-M08-20).

**Data**
- **Stored:** `news_item` (title, snippet ≤ 300 characters, grade), `news_company`, and `news_source.channel` (ir_rss, finnhub, massive, trade, sec_8k).
- 97% of Finnhub items are grade C (DS4).
- The Gemini labelling path exists (D21; the headline is the quote).
- Weekly counts are cheap.

### Worked example (illustrative; invented counts)
MU, week of 2026-10-05:
- 14 press items against a 26-week median of 6 → attention 2.3×.
- Labels: 6 positive, 2 negative, 6 neutral → tone (6 − 2) ÷ 14 = +0.29.
- Not an earnings week.

Signal record: `{ticker: "MU", module_id: "M08", signal: "news_attention", value: 2.3, timeframe: "ST", evidence_grade: "B", source_ref: "news_item ids …", method: "press count ÷ 26-wk median", as_of: "2026-10-09"}`

### All cases
1. **Normal week with press items:** attention and tone.
2. **Earnings week:** flagged, and compared with the own earnings-week median.
3. **Company-voice items** (`ir_rss`, `sec_8k`): excluded from tone and counted separately.
4. **Syndicated duplicates:** removed by the existing dedupe (D-M02-58).
5. **History shorter than 26 weeks** (the store started with M02 part 7a): attention missing until enough weeks exist (minimum set at build).
6. **Fetch succeeded with zero press items:** a real zero. A failed fetch is missing.
7. **Gemini label fails quote verification:** the item is unlabelled and left out of tone.
8. **Only grade-C items that week:** tone graded C.
9. **Recession regime** (S-new-M08-38): context note only.
10. **Signal combination:** the per-timeframe weights below. All signals are shown everywhere (D10).

### Suggestions
- **S6.1** `news_attention` = weekly distinct press items (non-company channels) ÷ own 26-week median, with earnings weeks flagged.
- **S6.2** `news_tone` = weekly (positive − negative) ÷ items, over press headlines labelled per Q6.1. It inherits the best item grade (B or C).
- **S6.3** Starting weights, tuned after a backtest:

| Signal group | MY | PT | ST |
|---|---|---|---|
| Valuation (headline, percentiles, normalized, PEG) | High | Medium | Low |
| Estimate revisions and dispersion | Low (M01) | Medium | Medium |
| Short interest, DTC | Info | Medium | Medium |
| Options skew and IV | Info | Low | Medium |
| News tone | Info | Low | Medium |
| News attention, crowding | Warning | Warning | Warning |

- **S6.4** Review queue (D8), capped weekly:
  - cyclical-flag proposals;
  - stage headline overrides;
  - guidance-versus-estimate conflicts.

### Failure modes
| Indicator | How it misleads | Guard |
|---|---|---|
| Tone of company releases | IR and 8-K text is uniformly upbeat | Exclude `ir_rss` and `sec_8k` from tone; count them separately |
| Headline only | The headline is not the article | Low weight; snippet as context |
| Syndication | Duplicates inflate attention | Existing dedupe (D-M02-58) |
| LLM labels | Bias and knowledge leakage (S82) | Measure against the owner's blind labels first (D-M02-40 lesson) |
| Short half-life | Daily tone fades within days (S-new-M08-39) | MY weight ≈ 0; weekly aggregate for PT |
| Scheduled news | Earnings weeks spike attention | Flag them; compare with the own earnings-week median |

### Questions
- **6.1 Tone method.**
  - a) Gemini headline labels, measured first against 100 owner blind labels.
  - b) The LM dictionary, after asking the authors about personal use.
  - c) Attention only, no tone.
  - Why (a): the path exists and is verified (D21), and LLM scores have return evidence (S-new-M08-40).
- **6.2 Company-voice items.**
  - a) Excluded from tone and counted separately.
  - b) Included.
  - Why (a): releases are uniformly upbeat and would swamp the press tone.
- **6.3 Weights.**
  - a) The table above as a start, tuned by backtest.
  - b) Equal weights.
  - c) The owner sets them.
  - Why (a): it follows each signal's evidence horizon (Rounds 1–5).

---

## Signals out (proposed, D13)
`module_id` = "M08" throughout. "Info" = shown, not scored. Each row has a reason-code partner when no value is computed.

| Signal | Value | Grade | MY | PT | ST | Round |
|---|---|---|---|---|---|---|
| `valuation_headline` | multiple; method names measure, basis and stage | A | High | Medium | Low | 1 |
| `valuation_pctile_own`, `valuation_pctile_peer` | 0–100 | A | High | Medium | Low | 1 |
| `valuation_reason` | code (`not_meaningful`, `stage_missing`, "EV incomplete" …) | A | Info | Info | Info | 1 |
| `valuation_ceiling_hit` | warning (M01 rule 4, D16) | A | Warning | Warning | Warning | 1 |
| `valuation_normalized` | multiple on cycle-average earnings | A | High | Medium | Low | 2 |
| `cyclical_flag` | bool, owner-confirmed | A | Info | Info | Info | 2 |
| `peg`, `peg_reason` | ratio or code | B (vendor growth) | Medium | Medium | Low | 2 |
| `est_revision_30d`, `est_revision_90d` | % | B | Low | Medium | Medium | 3 |
| `est_breadth_30d` | −1 to +1 | B | Low | Medium | Medium | 3 |
| `est_dispersion` | % of \|avg\|; warning only with M04 stress | B | Low | Medium | Medium | 3 |
| `est_coverage` | count | B | Info | Info | Info | 3 |
| `rec_change_3m` | change in mean score | B | Low | Medium | Medium | 3 |
| `eps_surprise` | % (vendor basis) | B | Low | Medium | Medium | 3 |
| `si_pct_shares`, `dtc`, `si_change_3m`, `si_pctile_own` | %, days, %, 0–100 | A or B (Q4.3) | Info | Medium | Medium | 4 |
| `short_volume_share` | % of off-exchange volume | A or B | — | Context | Context | 4 |
| `smirk`, `cp_spread`, `iv_change_1m` | pp | B (computed) | Info | Low | Medium | 5 (deferred) |
| `news_attention` | × own median | B or C | Warning | Warning | Warning | 6 |
| `news_tone` | −1 to +1 | B or C | Info | Low | Medium | 6 |

## Build parts (proposal)
Each part is one conversation at Medium effort, on branch `m08-partN`, with fixture tests.
- The module doc `docs/M08_SENTIMENT_VALUATION.md` (and DATA_SOURCES.md where relevant) is updated in the same commit.
- Each part has one combined owner live check of a few minutes, with the log sent back. Claude cannot call SEC.
- No new packages are expected.

| Part | Contents | Depends on | Live check (one per part) |
|---|---|---|---|
| 1 Valuation core | Concept migration (S1.5, deduplicated against M04 part 1); as-of engine (S1.3); every measure with reason codes; own and peer percentiles; stage headline (S1.1, 1.1); MSTR mode (1.3); signal writes | M04 part 1 (`facts_as_of`, `signal` writer); M04 part 2 soft (stage, peers; else `stage_missing` and own history only) | `uv run python scripts/run_live.py m08-valuation`: new concepts for the 16 tickers; MSTR digital-asset tag; GFS ifrs-full and 6-K coverage; INFQ recast series and both FY2025 net-income figures |
| 2 Estimates and recommendations | `estimate_snapshot`; Alpha Vantage weekly rotation ≤ 5/day (3.2); `EARNINGS` surprises; Finnhub recommendations; S3.2 signals; guidance-vs-estimate notes | M02 Alpha Vantage client and budget; R19 ledger | Probe `EARNINGS_ESTIMATES` and `EARNINGS` for the watchlist: coverage of INFQ, SPCX, GFS; fiscal mapping for MU, NVDA, MSFT; null fields |
| 3 PEG, cyclical flag, normalized valuation | S2.1–S2.5; review-queue proposals; interim normalization (2.4a) | Parts 1–2; M04 part 8 later | A report on the real DB that reproduces the MU 2022–25 and NVDA rows above from stored data |
| 4 Short interest | `short_interest` table; Massive with FINRA fallback (4.1); daily short-volume files (4.2); S4.2 signals; hedging label | Part 1 (as-of shares); M04 part 5 soft | Massive Basic short-interest probe for 3 tickers, plus one FINRA daily file |
| 5 News attention and tone | S6.1–S6.2; company-voice split; Gemini labels with quote verification after 100 owner blind labels (6.1) | M02 part 7a (built) | Gemini run on 100 headlines: agreement with the blind labels and cost |
| 6 Assembly and UI | Per-timeframe weights (6.3); weekly review caps (S6.4); valuation ceiling (S1.6); M08 tab, tested on scratch data in the Browser pane | Parts 1–5 | One logon catch-up run including the M08 steps within the 3-hour task limit; the run report lists missing snapshots |
| 7 Options (only if 5.1b) | IV computation (S5.2) | Q5 decided with M12 | Massive Options Basic probe: daily summary and contracts reference |

## Known gaps
1. **Unverified source claims.**
   - Findings marked "not re-read" rest on known abstracts with DOIs confirmed through Crossref.
   - The Boehmer et al. 1.16% figure has since been confirmed through an abstract mirror.
2. **Massive Basic and short interest.** The docs page and the pricing page conflict; a probe is needed.
3. **Alpha Vantage.**
   - The 25/day limit is taken from DATA_SOURCES and was not re-checked.
   - `EARNINGS_ESTIMATES` was tested only with the IBM demo key; watchlist coverage needs a probe.
4. **Rule 13f-2 / Form SHO** status was not verified, because the SEC pages returned 404.
5. **Unchecked filings data:** MSTR's bitcoin fair-value XBRL tag, the GFS IFRS taxonomy and INFQ's predecessor series.
   - The GFS gap (20-F, quarters in 6-K, annual multiples only) is not in any register yet; add it to DATA_SOURCES.
6. **Missing, not zero:** MSTR short interest as a % of shares (no shares tag); INFQ EV and TTM net loss.
7. **Round 6 example.** Real watchlist headlines and tone counts need the stored news, which Claude may not read (`data\`), so the example is illustrative.
8. **Prices** are from the Yahoo chart API (other); MU, NVDA and INFQ closes were re-checked. They will be replaced from `price_bar` at build.
9. **INFQ companyconcept figures** were not re-checked, because Claude does not call SEC. This covers FY2025 net income in both filings and the revenue split. Confirm them in the part 1 live run, including that TTM revenue uses one series.
10. **Weekly news history** is shorter than 26 weeks until the M02 part 7a store matures, so `news_attention` starts missing.
11. **No backtest yet.** Every weight and threshold is a starting value.

## New sources
Provisional IDs. They become the next S-numbers after M04's S-new-n are assigned. [peer-reviewed] unless marked otherwise.

- **S-new-M08-1** Liu, J., Nissim, D. & Thomas, J. (2002), "Equity Valuation Using Multiples", Journal of Accounting Research 40(1):135–172 — https://doi.org/10.1111/1475-679X.00042 · PDF https://business.columbia.edu/sites/default/files-efs/pubfiles/318/Equity_Valuation_Using_Multiples.pdf
- **S-new-M08-2** Basu, S. (1977), "Investment Performance of Common Stocks in Relation to Their Price-Earnings Ratios", Journal of Finance 32(3):663–682 — https://doi.org/10.1111/j.1540-6261.1977.tb01979.x
- **S-new-M08-3** Loughran, T. & Wellman, J. (2011), "New Evidence on the Relation between the Enterprise Multiple and Average Stock Returns", JFQA 46(6):1629–1650 — https://doi.org/10.1017/S0022109011000445
- **S-new-M08-4** Barbee, W., Mukherji, S. & Raines, G. (1996), "Do Sales–Price and Debt–Equity Explain Stock Returns Better than Book–Market and Firm Size?", Financial Analysts Journal 52(2):56–60 — https://doi.org/10.2469/faj.v52.n2.1980
- **S-new-M08-5** Trueman, B., Wong, M.H.F. & Zhang, X.-J. (2000), "The Eyeballs Have It: Searching for the Value in Internet Stocks", Journal of Accounting Research 38 (Supplement):137–162 — https://doi.org/10.2307/2672912
- **S-new-M08-6** Easton, P. (2004), "PE Ratios, PEG Ratios, and Estimating the Implied Expected Rate of Return on Equity Capital", The Accounting Review 79(1):73–95 — https://doi.org/10.2308/accr.2004.79.1.73
- **S-new-M08-7** Bradshaw, M. (2004), "How Do Analysts Use Their Earnings Forecasts in Generating Stock Recommendations?", The Accounting Review 79(1):25–50 — https://doi.org/10.2308/accr.2004.79.1.25
- **S-new-M08-8** Beaver, W. & Morse, D. (1978), "What Determines Price-Earnings Ratios?", Financial Analysts Journal 34(4):65–76 — https://doi.org/10.2469/faj.v34.n4.65
- **S-new-M08-9** Penman, S. (1996), "The Articulation of Price-Earnings Ratios and Market-to-Book Ratios and the Evaluation of Growth", Journal of Accounting Research 34(2):235–259 — https://business.columbia.edu/faculty/research/articulation-price-earnings-ratios-and-market-book-ratios-and-evaluation-growth · CFA digest [other] https://rpc.cfainstitute.org/research/cfa-digest/1997/05/the-articulation-of-priceearnings-ratios-and-market-to-book-ratios-and-the-evaluation-of-growt
- **S-new-M08-10** Chan, L., Jegadeesh, N. & Lakonishok, J. (1996), "Momentum Strategies", Journal of Finance 51(5):1681–1713 — https://doi.org/10.1111/j.1540-6261.1996.tb05222.x
- **S-new-M08-11** Jegadeesh, N., Kim, J., Krische, S. & Lee, C. (2004), "Analyzing the Analysts: When Do Recommendations Add Value?", Journal of Finance 59(3):1083–1124 — https://doi.org/10.1111/j.1540-6261.2004.00657.x
- **S-new-M08-12** Womack, K. (1996), "Do Brokerage Analysts' Recommendations Have Investment Value?", Journal of Finance 51(1):137–167 — https://doi.org/10.1111/j.1540-6261.1996.tb05205.x
- **S-new-M08-13** Barber, B., Lehavy, R., McNichols, M. & Trueman, B. (2001), "Can Investors Profit from the Prophets?", Journal of Finance 56(2):531–563 — https://doi.org/10.1111/0022-1082.00336
- **S-new-M08-14** Diether, K., Malloy, C. & Scherbina, A. (2002), "Differences of Opinion and the Cross Section of Stock Returns", Journal of Finance 57(5):2113–2141 — https://doi.org/10.1111/0022-1082.00490
- **S-new-M08-15** Avramov, D., Chordia, T., Jostova, G. & Philipov, A. (2009), "Dispersion in Analysts' Earnings Forecasts and Credit Rating", Journal of Financial Economics 91(1):83–101 — https://doi.org/10.1016/j.jfineco.2008.02.005
- **S-new-M08-16** Richardson, S., Teoh, S.H. & Wysocki, P. (2004), "The Walk-down to Beatable Analyst Forecasts", Contemporary Accounting Research 21(4):885–924 — https://doi.org/10.1506/KHNW-PJYL-ADUB-0RP6
- **S-new-M08-17** Hong, H., Lim, T. & Stein, J. (2000), "Bad News Travels Slowly: Size, Analyst Coverage, and the Profitability of Momentum Strategies", Journal of Finance 55(1):265–295 — https://doi.org/10.1111/0022-1082.00206
- **S-new-M08-18** Bernard, V. & Thomas, J. (1989), "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?", Journal of Accounting Research 27 (Supplement):1–36 — https://doi.org/10.2307/2491062
- **S-new-M08-19** [primary] Alpha Vantage API documentation (Premium markers) and `EARNINGS_ESTIMATES` demo response, checked 2026-10-12 — https://www.alphavantage.co/documentation/ · https://www.alphavantage.co/query?function=EARNINGS_ESTIMATES&symbol=IBM&apikey=demo
- **S-new-M08-20** [primary] Finnhub OpenAPI specification (premium and free-tier fields), checked 2026-10-12 — https://finnhub.io/static/swagger.json
- **S-new-M08-21** Asquith, P., Pathak, P. & Ritter, J. (2005), "Short Interest, Institutional Ownership, and Stock Returns", Journal of Financial Economics 78(2):243–276 — https://ideas.repec.org/a/eee/jfinec/v78y2005i2p243-276.html
- **S-new-M08-22** Boehmer, E., Jones, C. & Zhang, X. (2008), "Which Shorts Are Informed?", Journal of Finance 63(2):491–527 — https://doi.org/10.1111/j.1540-6261.2008.01324.x
- **S-new-M08-23** [other, working paper] Hong, H., Li, W., Ni, S., Scheinkman, J. & Yan, P. (2015), "Days to Cover and Stock Returns", NBER w21166 — https://www.nber.org/papers/w21166
- **S-new-M08-24** Diether, K., Lee, K.-H. & Werner, I. (2009), "Short-Sale Strategies and Return Predictability", Review of Financial Studies 22(2):575–607 — https://doi.org/10.1093/rfs/hhn047
- **S-new-M08-25** Choi, D., Getmansky, M. & Tookes, H. (2009), "Convertible Bond Arbitrage, Liquidity Externalities, and Stock Prices", Journal of Financial Economics 91(2):227–251 — https://ideas.repec.org/a/eee/jfinec/v91y2009i2p227-251.html
- **S-new-M08-26** Hong, H., Scheinkman, J. & Xiong, W. (2006), "Asset Float and Speculative Bubbles", Journal of Finance 61(3):1073–1117 — https://doi.org/10.1111/j.1540-6261.2006.00867.x
- **S-new-M08-27** Rapach, D., Ringgenberg, M. & Zhou, G. (2016), "Short Interest and Aggregate Stock Returns", Journal of Financial Economics 121(1):46–65 — https://doi.org/10.1016/j.jfineco.2016.03.004
- **S-new-M08-28** [primary] FINRA, checked 2026-10-12:
  - equity short interest (Rule 4560) — https://www.finra.org/finra-data/browse-catalog/equity-short-interest
  - daily short-sale volume files — https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files
  - API documentation — https://developer.finra.org/docs
- **S-new-M08-29** [primary] Massive, checked 2026-10-12:
  - short interest — https://massive.com/docs/rest/stocks/fundamentals/short-interest
  - option-chain snapshot — https://massive.com/docs/rest/options/snapshots/option-chain-snapshot
  - options daily ticker summary — https://massive.com/docs/rest/options/aggregates/daily-ticker-summary
  - pricing — https://massive.com/pricing
- **S-new-M08-30** [other] Nasdaq quote short-interest API (undocumented; example only; URL not recorded)
- **S-new-M08-31** Xing, Y., Zhang, X. & Zhao, R. (2010), "What Does the Individual Option Volatility Smirk Tell Us About Future Equity Returns?", JFQA 45(3):641–662 — https://doi.org/10.1017/S0022109010000220
- **S-new-M08-32** Cremers, M. & Weinbaum, D. (2010), "Deviations from Put-Call Parity and Stock Return Predictability", JFQA 45(2):335–367 — https://doi.org/10.1017/S002210901000013X
- **S-new-M08-33** Bali, T. & Hovakimian, A. (2009), "Volatility Spreads and Expected Stock Returns", Management Science 55(11):1797–1812 — https://doi.org/10.1287/mnsc.1090.1063
- **S-new-M08-34** An, B.-J., Ang, A., Bali, T. & Cakici, N. (2014), "The Joint Cross Section of Stocks and Options", Journal of Finance 69(5):2279–2337 — https://doi.org/10.1111/jofi.12181
- **S-new-M08-35** Tetlock, P. (2007), "Giving Content to Investor Sentiment: The Role of Media in the Stock Market", Journal of Finance 62(3):1139–1168 — https://doi.org/10.1111/j.1540-6261.2007.01232.x
- **S-new-M08-36** Tetlock, P., Saar-Tsechansky, M. & Macskassy, S. (2008), "More Than Words: Quantifying Language to Measure Firms' Fundamentals", Journal of Finance 63(3):1437–1467 — https://doi.org/10.1111/j.1540-6261.2008.01362.x
- **S-new-M08-37** Loughran, T. & McDonald, B. (2011), "When Is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks", Journal of Finance 66(1):35–65 — https://doi.org/10.1111/j.1540-6261.2010.01625.x · licence page [primary] https://sraf.nd.edu/loughranmcdonald-master-dictionary/
- **S-new-M08-38** García, D. (2013), "Sentiment during Recessions", Journal of Finance 68(3):1267–1300 — https://doi.org/10.1111/jofi.12027
- **S-new-M08-39** Heston, S. & Sinha, N. (2017), "News vs. Sentiment: Predicting Stock Returns from News Stories", Financial Analysts Journal 73(3):67–83 — https://doi.org/10.2469/faj.v73.n3.3
- **S-new-M08-40** [other, working paper] Lopez-Lira, A. & Tang, Y., "Can ChatGPT Forecast Stock Price Movements? Return Predictability and Large Language Models", arXiv 2304.07619 (v6, Oct 2025) — https://arxiv.org/abs/2304.07619
- **S-new-M08-41** [primary] FINRA consolidated daily short-sale volume file, 2026-10-09 — https://cdn.finra.org/equity/regsho/daily/CNMSshvol20261009.txt
- **S-new-M08-42** [primary] FASB ASU 2023-08, Intangibles—Goodwill and Other—Crypto Assets (fair value). URL to add at build.
- **S-new-M08-43** [other] Yahoo Finance chart API, daily closes (MU, NVDA, INFQ re-checked 2026-10-12; replaced from `price_bar` at build) — https://query1.finance.yahoo.com/v8/finance/chart/
- **S-new-M08-44** [primary] Strategy Inc (MSTR, CIK0001050446) 10-Q, convertible notes outstanding. URL to add at build.
- **S-new-M08-45** [primary] FRED, 10-Year Treasury Constant Maturity Rate (DGS10). Named in the research and not checked this session — https://fred.stlouisfed.org/series/DGS10

**Reused IDs:** S11, S18, S35, S68, S82, S91. From M04 (pending): S-new-1, S-new-2, S-new-9, S-new-10, S-new-55, S-new-56, S-new-67.
