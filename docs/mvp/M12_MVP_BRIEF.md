# M12 Options overlay — MVP brief
Updated 2026-10-13 · Source: docs/M12_DESIGN_PACK.md (research) · Status: for owner decision (one sitting)

Research signals, not financial or tax advice. **Brief-only for the MVP: built after the other MVP modules (DESIGN "Next action"). Gating question: DESIGN Q5 (free options data) = Q12.1.** D31 asks for MVP signals on stored data; R20's "IV high" test cannot run on anything stored, so M12 alone needs one new source. Without one, M12 gives only the calendar and the regime and thesis reads: every `cc_window` reads `insufficient_data` and `cc_template` is missing ("no IV source").

## Purpose in one paragraph
For a stock you hold, M12 shows when a covered call is a reasonable window and proposes an expiry and strike. Signals only, nothing enforced (R20, D8, D16). Binding: **R20** (window = regime weak/sideways, IV high against the stock's own history, no earnings inside the option's life; 30–45 DTE, about 15 delta, "index-derived"; tax notes informational), **R14** (wealth comes from a few big winners, S01; this is the basis for the thesis block in Q12.6, not a rule in itself), D10, D11/D12 (an overlay is a `position` row with `layer` = overlay and its own `profile_of_record`; the pack's "M12 overlay (ST)" default is a proposal, deferred with Round 6), D13/D14, D27 and M01 rules 3/7 (σ add trigger), S1, S2. **Read from other MVPs, never rebuilt:** M09 `trend_state` and `band_z` (M09's brief lists R20 as an M12 reader), M04 `survival_gate`, `filing_status`, `non_reliance`, `gc_language`, `cvd_state`, M10's FRED client, and M11's `lot` entry. **Outline check:** the outline has no options section. Its only options text is Technical Analysis item 3: σ bands "will aid in selling calls at tops and selling puts at bottoms". The pack (written before the outline was in the repo) covers covered calls under R20 only; the MVP follows R20 and shows the σ position as info. Q12.5 offers "tops" as a D6 change; Q12.8 covers "puts at bottoms".

## Data already stored that the MVP uses
| Need | Stored where (code) | Gap |
|---|---|---|
| Closes, adjusted closes, `div_cash`, `split_factor` | `price_bar` (0012; `prices/store.py` `bars()` with weekly bars), grade A (D-M04-82) | — |
| Regime and σ position | M09 MVP signals `trend_state` (up/flat/down: close against the 40-week MA plus slope, 2-close flip) and `band_z` (signed z from the 20-week mean, `below_2`…`above_2`), read with `signals.latest_signal` | Not built (M09 MVP). Fallback only if M09 drops them: Q12.5 |
| rv20 (20-day realized volatility) | Computed from `price_bar` daily `adj_close` | Small helper, new (M09 defers its volatility panel) |
| Past earnings dates and times | `event` 2.02 + `accepted_at` (0006); `calls/transcripts.company_releases()` picks the results release per quarter and skips Tesla's deliveries 2.02 | — |
| Announced earnings dates | `news_item` / `news_source` (`ir_rss`, A) / `news_company` (0025): headlines and snippets, not parsed for dates | Parser is new |
| Event blocks | `signal` (0029: `cik`, `value_text`): `survival_gate`, `filing_status`, `non_reliance` (built); `gc_language` (4b-lite), `cvd_state` (8a); `event` 1.03 and 4.02 | — |
| Budgets | `fetch_log`; lane `massive` in `news/fetch.py` (12.5 s; news backup only today); `calls/alpha_vantage.py` (25 a day, run 20) | — |
| Option prices, IV history | none | **DS5** (Q5) |
| Cboe single-stock VIX (AAPL, AMZN, GOOG), VIX, T-bill rate | FRED; no client in code yet. M10's MVP builds `src/engine/macro/fred.py` (keyless CSV, S-new-M10-17) | M12 adds 5 series to M10's client (~5 requests a day) |
| Upcoming ex-dividend dates | Past ex-dates in `div_cash` only; next estimated by cadence | New gap (ID at build, after M07's) |
| Lots and positions | `position` (`layer` core/overlay, `profile_of_record`), `lot` (`acquired_on`, `quantity`), `decision` (0001); empty until M11's MVP adds hand entry | Coverable check (open lots ≥ 100 shares) reads them; overlay ledger and tax panel deferred (Round 6) |

## MVP signals (4)
D13 rows keyed by `cik` (ticker for display, D-M04-74), one per timeframe, written by `signals.write_signal`; states in `value_text`; missing = `value` and `value_text` empty and `method` "missing: <reason>"; grade = weakest deciding input; `source_ref` = the deciding document or series ("FRED VXAPLCLS 2026-10-08", an 8-K accession, a `news_item` link), "+N" when more (D-M04-9). ✓ = may carry weight; info = 0.

| Signal | value / value_text | Meaning | Inputs | MY | PT | ST | Grade rule |
|---|---|---|---|---|---|---|---|
| `cc_window` | text: open, closed_regime, closed_iv_low, blocked_event, blocked_thesis, blocked_earnings, insufficient_data; reason list in `method` | Covered-call window (R20); order when several apply: blocked_event > blocked_thesis > blocked_earnings > insufficient_data > closed_regime > closed_iv_low; opens after 2 passing days (S5.4) | The three signals below; M04 rows; M09 `trend_state` (Q12.5) and `band_z` (Q12.6) | info | ✓ | ✓ | Weakest deciding input; a cadence-estimated date makes it C |
| `next_earnings` | value = calendar days to the date; text "2026-11-02 amc confirmed" | Earnings date used by the block | IR headline (Q12.4), Alpha Vantage calendar, cadence from 2.02 | info | info | info | A: company notice or 8-K; B: vendor; C: cadence estimate |
| `iv_pct_252` | 0–100, or missing "insufficient history (n/252)". `method`: iv30, source, n, event days excluded, rank, rv20, `iv_rv_gap` | IV against the name's own history (R20), plus IV against realized volatility | FRED Cboe series or our own snapshot (Q12.1); `price_bar` | info | ✓ | ✓ | A: Cboe via FRED; B: computed by the engine |
| `cc_template` | value = approximate premium per share; text "2026-12-18 C380" (+ "assumed strike" when there is no grid) | Monthly in 31–45 DTE (Q12.7), first listed strike ≥ approx. 15-delta. `method`: % OTM, upside cap, risk-neutral P(ITM), DTE > 30 check, ex-dividend warning, "index-derived; skew not modelled; before costs" | iv30, close, rate, dividend yield, strike grid | info | info | info | B (computed) |

Claim line on every row (S1.1): "Single-stock options carry little volatility premium on average (S-new-M12-2); this window is a timing signal, not an expected edge."

## Worked example (real figures from the pack unless marked illus.)
**AAPL on 2026-10-08.**
- VXAPL (FRED) 27.90; 252-day low 18.57, high 35.77; rank 54.2, percentile 54.2. VIX 15.41 (percentile 17.1) is market context only, never AAPL's reading.
- Next earnings 2026-11-02 (Apple IR via S-new-M12-18; grade A once the IR headline is matched). The Nov-20 monthly (43 DTE) contains it → **`blocked_earnings`**; first eligible: Dec-18 (45 DTE from 2026-11-03). The 27.90 includes the print, so it is flagged (Q12.3a).
- VXAPL the day after each print: −10.5% (2025-10-30), −19.4%, −18.4%, −11.1% (2026-07-30).
- `iv_rv_gap` with rv20 = 22.0 (illus.; bars not readable by Claude) = +5.9 points.

**Template arithmetic** (S 340.42 from a one-off public check, S-new-M12-21, to be replaced by the stored Tiingo bar; σ 27.9%, T 43/365; rate 4.0% and yield 0.3% illus.; re-computed): 15-delta strike 379.3 (11.4% OTM), value $2.43, risk-neutral P(ITM) 12.9%. At an assumed $380 strike: ≈ $2.34 (0.69%), delta 0.146, P(ITM) 12.5%, upside cap +11.6%. Labelled "approx., skew not modelled, index-derived".

**SPCX.** Options from 2026-06-16 → "insufficient history (80/252)", never 0. Before its first print (2026-08-04) ATM IV was ≈ 129–156% against 59.4% rv20 (S-new-M12-19); closed until after the print.

**MU (illus.).** `trend_state` down, percentile 72, IV above rv20, no earnings in the life → would open. But if `band_z` reads `below_1` with the gate not failing (M01 rule-3 add trigger; CvD added once 8a lands) → `blocked_thesis` (Q12.6).

## Cases the rules must handle
- All tests pass 2 days running → `open`; the first failure closes it. Each recompute is logged.
- Regime up → `closed_regime`. IV not high (Q12.3) → `closed_iv_low`.
- Earnings in [today, expiry + 1 trading day], any status → `blocked_earnings`. A cadence estimate blocks ±7 days. An unknown time of day blocks that day.
- Date moves → re-checked daily, old and new dates in `method`. Sources disagree → the newest confirmed date wins, both shown (no review kind).
- Tesla's deliveries 8-K (also 2.02) → not an earnings date (`company_releases` timing; LESSONS).
- Under 2 past results releases and no notice → `blocked_earnings` "date unknown", grade C (S-new-M12-6).
- `non_reliance` open, Item 1.03, `gc_language` going concern, gate fail or filing overdue → `blocked_event`. Gate incomplete / not_applicable → "not evaluated", no block.
- An input module not built yet (4b-lite, 8a, M09) → "not evaluated", never "passed".
- M01 rule-3 add trigger active (Q12.6) → `blocked_thesis`. M11's MVP has no "accumulate" state (its `thesis_state` is no_thesis / early / on_track / review / exit_warning), so the M11 reading waits for tuning.
- Under 126 IV days → `insufficient_data`; 126–251 → "provisional". Event-window days are kept out of the distribution (count shown), and today's reading is flagged.
- Cboe names → FRED only, never spliced; our own AAPL IV is stored as calibration.
- Call or put with zero volume → the other one, flagged. Both zero, or no expiry near 30 days → day missing. Call/put IV gap > 5 points (starting value) → stale flag.
- PC-off days → backfilled from Massive's 2-year history. Holiday → no row. `split_factor` ≠ 1 or adjusted contracts → excluded. Missing bars → rv20 missing, never 0.
- SPCX → n/252 shown. ETV → "missing: not applicable (fund writes its own calls)" (2.3a). INFQ → missing until the probe confirms options.
- No monthly in 31–45 DTE → a weekly. No strike grid → "assumed" strike. Never ≤ 30 DTE if Q12.7a.
- Estimated ex-dividend before expiry → warning in `cc_template`, not a block (4.2a).
- No holding or < 100 shares in open `lot` rows → still shown (D10), "not coverable (n shares)"; no lots entered → "coverable: not evaluated (no lots stored)".
- Budget stop → reported, resumes next logon; a partial day stays missing. Vendor terms re-checked at each probe (D-M02-59).
- **How this could mislead (D9), with the guard:** index evidence read as a single-stock edge → claim line, "index-derived" · a print inflating the percentile → event days excluded · stale last-trade closes → volume > 0, call/put check · risk-neutral P(ITM) read as real → label · regime rule read as an edge → "owner rule (R20)" (S29) · high IV because risk is high → event blocks · cadence date taken as confirmed → grade C · an open window read as an instruction → D16 wording · licences (Tiingo S68, FRED's Cboe notice, Massive individual use) → nothing is shared.

## Deferred to the tuning phase
- `vrp_hist`, own premium by year (S1.2, 1.1): needs long history; context only.
- Cao & Han high-idiosyncratic note (1.2): needs a factor regression.
- `iv_event_share` (S3.1, S4.5) and a constant-maturity iv30 from two expiries (S2.2): double the calls. The MVP uses the monthly nearest 30 days, "approx. 30-day".
- 1- and 3-year percentiles (MSTR); `iv_rank_252` as its own signal (kept in `method`).
- `m12_date_conflict` review kind; curated other events (4.3); put-vs-dividend check (needs chains).
- Round 6 in full (overlay ledger on `position`/`lot`, deep-in-the-money benchmark, holding-period suspension, FIFO / specific-ID, lots under 1 year, forgone upside, Pub 550, wash sales): needs lots entered (M11 MVP) and a written overlay. The MVP keeps only the DTE > 30 check and the coverable share count.
- M11 thesis reading for the thesis block (needs a state the owner names; M11's MVP has none for "accumulate").
- Outline TA 3 "selling puts at bottoms" (Q12.8a) as a D6 proposal with sources.
- Skew model; Alpaca / Tradier / Massive Starter; 1–2-year backfill.

## Questions for the owner
**Q12.1 IV source (closes DESIGN Q5 and DS5)**
- (a) *Recommended.* FRED Cboe series for AAPL, AMZN, GOOG (full history, ~5 requests a day on M10's client); for the 11–12 other optionable names, our own daily snapshot from Massive Options Basic closes (ATM call and put, one expiry, binomial IV). Why: $0, no new account, grade A/B (S-new-M12-9, -11); ≈ 26 calls at 12.5 s ≈ 5.5 min a day in the logon run (count to probe).
- (b) FRED names only; the other 12 show "missing: no IV source", so their window is `insufficient_data`.
- (c) Alpaca indicative feed (account you open; history only from 2024-02; S-new-M12-12).
- (d) A paid feed (changes S2).

**Q12.2 History depth for our own snapshot (only if Q12.1a or c)**
- (a) *Recommended.* Owner-run 6-month backfill (12 × 126 days × 2 calls ≈ 3,000 calls ≈ 10.5 h at 12.5 s, plus reference calls for expired contracts, in ~2-h sessions outside the refresh; backfills are owner-run, D-M04-70), then daily. The pack recommended 1 year (2.2a); 6 months is the MVP cut. Why: a provisional percentile at once, 252 days six months later.
- (b) Forward only: our own names stay `insufficient_data` for about 6 months.
- (c) 1 year (≈ 22 h).

**Q12.3 What "IV high" means for the window**
- (a) *Recommended.* Percentile ≥ 50, event days excluded, **and** IV > rv20. Why: R20's own-history test plus the peer-reviewed IV-vs-realized test (S-new-M12-5, -17); prints inflate pre-print readings (S-new-M12-7). The IV > rv20 condition adds to R20's wording, so it is a D6 change.
- (b) Percentile ≥ 50 only, event days kept in.
- (c) Percentile ≥ 70.

**Q12.4 Earnings-date sources**
- (a) *Recommended.* IR headline (A) > one Alpha Vantage `EARNINGS_CALENDAR` call a week (B; free access to probe) > cadence (C, ±7 days); all block. Why: IR notices often come too late for a 45-day option; a miss costs the event risk (S-new-M12-6).
- (b) IR headline and cadence only, with no vendor call.
- (c) Only confirmed dates block; estimates only warn.

**Q12.5 Regime test, and the outline's "selling calls at tops"**
- (a) *Recommended.* R20 as approved, read from M09: weak = `trend_state` down, sideways = flat; `band_z` shown as info. Only if M09 does not build `trend_state`: weekly close < 40-week MA, or the MA's 10-week change within ±2% (starting value, unsourced), labelled "provisional". Why: R20 binds; one regime reading engine-wide (M09's brief names M12 as its reader); no source shows a band rule helps (S29).
- (b) Add the outline rule under D6: the window may also open in an up regime when `band_z` reads `above_1` or `above_2` ("tops"; M09 Q09.3 labels these for M12).
- (c) Require both a weak/sideways regime and `band_z` ≥ `above_1`.

**Q12.6 Do not cap a name in its add zone**
- (a) *Recommended.* Block (`blocked_thesis`) when M01's rule-3 add trigger is active: `band_z` `below_1` or `below_2`, `survival_gate` pass or warn, and, once Part 8a lands, `cvd_state` CYCLICAL_TROUGH or NO_SLOWDOWN (D-M01-5). Until 8a merges, CvD is "not evaluated" and the block stands on the band and the gate. Why: R14 / S01 says do not cap an add candidate; a band touch on a failing name is not one (M01 rule 3).
- (b) Block on the σ band alone (≥ 1σ below the 20-week mean), whatever the gate and CvD say.
- (c) Warning only.

**Q12.7 DTE template**
- (a) *Recommended.* 31–45 DTE (changes R20 under D6). Why: a qualified covered call must be granted "more than 30 days" before expiry (26 USC 1092(c)(4)(B), S-new-M12-15).
- (b) Keep 30–45 as approved.

**Q12.8 Cash-secured puts at bottoms (outline Technical Analysis 3)**
- (a) *Recommended.* Not in the MVP; a D6 proposal with sources at tuning. Why: R20 covers covered calls only; puts need their own research.
- (b) Add a mirror `csp_window` in the MVP (≥ 1σ below the 20-week mean, IV high, no earnings).

Defaults unless struck: claim line (S1.1), ETV n/a (2.3a), own premium context only (1.1a), ex-dividend a warning (4.2a), 2-day hysteresis (S5.4).

## Build parts (after MVP)
**Part 1 — Options data and IV.**
- Code: the five series (VXAPLCLS, VXAZNCLS, VXGOGCLS, VIXCLS, DTB3) added to M10's `src/engine/macro/fred.py` (built in M10's MVP; if M10 has not merged, this part builds that file to M10's design); `options/snapshot.py` (Massive reference once per name and expiry, daily summaries, `fetch_log` budget); `options/iv.py` (CRR binomial, bisection); `options/realized.py` (rv20); `scripts/run_options.py probe | snapshot | backfill --hours N | --list`.
- Tables (migration TBD): `iv_obs` (symbol, date, expiry, strike, cp, opt_close, opt_volume, und_close, rate, div_model, iv), `iv_daily` (symbol, date, source, iv30, n, flags). No review kinds, no UI. Docs: `M12_OPTIONS.md`, DS5 rows, a LESSONS line on personal-use clauses.
- Live check (one command): `uv run python scripts/run_options.py probe`: FRED 5; Massive ≈ 16 (reference endpoint, INFQ/ETV listings, one day's snapshot for AAPL against VXAPL, TSLA and SPCX); Alpha Vantage `EARNINGS_CALENDAR` 1; SEC 0; ≈ 4 min.
- Fixtures: FRED CSV, Massive reference and summary replies, the solver against a known Black-Scholes value.

**Part 2 — Calendar, window, template, signals, Options tab.**
- Code: `options/calendar.py` (cadence via `company_releases`, IR headline regex, weekly Alpha Vantage pull, ex-dividend cadence); `options/window.py` (reads M09, M04 and lot rows; states, hysteresis); `options/template.py`; writer via `signals.write_signal`; local refresh step last in `scripts/run_refresh.py`, after `prices_step`, the M04 local steps and M09's signals, inside the lock. The weekly Alpha Vantage call counts against the shared 25-a-day `fetch_log` budget (the transcripts run keeps 20).
- Tables (migration TBD): `m12_event` (cik, kind, date, time, status, grade, source_ref), `m12_window_log`. No review kinds.
- UI: new company tab "Options": state and reasons, IV line (source, n, percentile, gap), next earnings with grade, template with labels and claim line; checked on scratch data (port 8799).
- Live check: `uv run python scripts/run_options.py window --no-net`: 0 requests, < 1 min, one line per name.
- Fixtures: AAPL earnings block, Tesla deliveries 2.02, SPCX insufficient, MU thesis block, gate fail.
- Depends on: M04 `survival_gate`, `filing_status`, `non_reliance` (built); `gc_language` (4b-lite), `cvd_state` (8a), "not evaluated" until merged; M09 `trend_state`, `band_z` (else the Q12.5a fallback); M10 FRED client; M11 lot entry (optional).

## Open risks
- Not verified: Massive Basic access to the contract-reference endpoint, its storage terms and real call count (if blocked, strikes are "assumed"); free Alpha Vantage `EARNINGS_CALENDAR`; INFQ options; FRED access route and Cboe notice for local storage.
- Our IV from last-trade closes may differ from Cboe's method (the AAPL calibration row measures it); no skew model, so the 15-delta strike is approximate.
- The `massive` lane is shared with the news backup; a Finnhub outage can delay the snapshot to the next logon.
- No lot data: "covered" and the tax panel cannot be checked in the MVP.
- Thin evidence: single-stock premium insignificant on average; regime rule is the owner's (S-new-M12-2, S29). The MVP claims timing only.
- S-new-M12-22: the pack's URL is complete and live (https://www.theocc.com/newsroom/press-releases/2015/05-08-new-academic-research-finds-options-based-in, checked 2026-10-13). The study is Hemler & Miller, "The Performance of Options-Based Investment Strategies: Evidence for Individual Stocks During 2003–2013". The release does not give the "ten stocks" sample size; confirm it from the study.

## Check notes (2026-10-13)
- **Outline fit.** TA 3 ("selling calls at tops and selling puts at bottoms") was already raised (Q12.5b/c, Q12.8). Puts at bottoms is now also listed under Deferred. The "tops" options now read M09's `band_z` (`above_1`/`above_2`, labelled for M12 by M09 Q09.3) instead of a new σ computation.
- **Binding decisions.**
  - R14 was stated as the rule "do not cap a future winner". R14 binds only the Bessembinder statement (S01), so it is now worded as the basis for Q12.6.
  - The overlay profile name "M12 overlay (ST)" was shown as binding under D11/D12. It is the pack's S6.1 proposal and is now marked as such.
  - Q12.3a adds IV > rv20 to R20's wording, and is now flagged as a D6 change.
  - Q12.6 called a 1σ band touch the "M01 rule 3 add zone". Rule 3 also needs the gate and CvD (D-M01-5). Option (a) is now the full rule-3 trigger, with CvD "not evaluated" until 8a; the band alone moved to option (b).
- **Data reality.**
  - "Lots and positions: none" was wrong. `position` (layer core/overlay, `profile_of_record`), `lot` and `decision` exist in engine migration 0001; they are empty until M11's MVP hand entry. The coverable check now reads them.
  - M11's MVP has no "accumulate" thesis state, so that reading moved to Deferred.
  - M10's MVP builds `src/engine/macro/fred.py`, so M12 adds series to it rather than creating the file.
  - The refresh hook now runs after the M04 local steps and M09 (all in `scripts/run_refresh.py`), not just "after `prices_step`".
  - The weekly Alpha Vantage call shares the 25-a-day budget.
  - D31's stored-data rule cannot be met for R20's IV test. This is now stated in the header.
  - Verified to exist: `price_bar` (0012), `event` (0006), `signal` with `cik`/`value_text` (0029), `fetch_log`, `news_item`/`news_source` `ir_rss` (0025), the `massive` lane at 12.5 s (`news/fetch.py`), `alpha_vantage.py` (25/20), `company_releases`, `prices.store.bars`, `signals.write_signal`/`latest_signal`, `prices_step`.
- **Numbers and sources.**
  - Re-computed the template (379.3 strike, $2.43, P(ITM) 12.9%; $380 → $2.34, delta 0.146, 12.5%, +11.6%), the VXAPL rank of 54.2 and the DTE counts (Nov-20 = 43, Dec-18 = 45 from Nov 3): all correct.
  - The 340.42 close is now marked as a one-off check (S-new-M12-21), to be replaced by the stored bar.
  - The Q12.2 count was corrected to ≈ 3,000 calls ≈ 10.5 h, with the extra reference calls noted.
  - The S-new-M12-22 URL was not cut off. It was confirmed live, and the risk line was updated; the "ten stocks" sample size is still unconfirmed.
  - All S-numbers cited exist in SOURCES.md or the pack.
- **MVP discipline.**
  - Already within limits: 4 signals, 8 questions, 2 parts.
  - Part 1's two live commands were merged into one probe (≈ 4 min).
  - The D13 line now gives the `source_ref` rule and the missing-row form (D-M04-9).
- **Overlap.**
  - The regime (`trend_state`) and σ position (`band_z`) come from M09's MVP; the brief no longer computes its own, apart from a fallback labelled provisional.
  - The M04 event blocks read the built signals; `filing_status` was added to Depends.
  - rv20 stays M12's own small helper, because M09 defers its volatility panel.
- **Length.** About 20k characters, above the 15k target. The D9 list was compressed; the remaining length is the case list the owner asked for.
