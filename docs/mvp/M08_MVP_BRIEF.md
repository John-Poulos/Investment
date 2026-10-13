# M08 Sentiment & valuation — MVP brief
**Decided 2026-10-13 → docs/M08_VALUATION.md** (D-M08-1…7; Q08.1a–Q08.7a, with Q08.3 changed to (b) — M08 computes normalized earnings power as the shared helper `financials/nep.py` — and the owner's standard-metrics amendment to Q08.1a, recorded as DESIGN D32). Kept as the sitting record.
Updated 2026-10-13 · Source: docs/M08_DESIGN_PACK.md (research) · Status: for owner decision (one sitting)

## Purpose in one paragraph
For every equity in every timeframe (D10), M08 answers: how expensive is the stock against its own history, on the measure that fits its stage, and which way are analysts moving their estimates? Outline sections served: "PEG" 1–2, "Analysts Price Targets and Upgrades" 1–4, "Technical Analysis" 1 (cheap is not a buy; valuation sits beside M04's gate). Binding revisions: **R6** (PEG only when EPS > 0 and growth > 0; a sales-based fallback; flag cyclicals) and **R15** (revisions and dispersion, not price-target levels; S11). M01 gives analysts **low** (not zero) weight in MY; rule 4's valuation ceiling needs positions (M11). The MVP **departs from the outline** in three places:
- Analysts item 2 "spread of targets" becomes the spread of EPS estimates: R15 rules out target levels and no free target feed exists.
- Analysts item 5 "crowded consensus" is deferred; M02's theme crowding flag (D-M02-10) and the analyst count in `est_revision` stand in.
- Ownership item 4 (short interest) belongs to M07 (D15) and is asked once, in **Q07.8**; M08 pack Round 4 is the research behind it.

## Data already stored that the MVP uses
- **Facts:** `fact` (every companyfacts tag, all taxonomies) via `facts_as_of` (`sec/asof.py`; XBRL 6-K for 20-F filers, INFQ de-SPAC boundary). Mapped concepts (`sec/xbrl_facts.py`) cover every input: revenue, gross profit, operating and net income, EPS, D&A, cash and investments, the debt concepts, preferred, equity, `crypto_fair_value`, `shares_cover`, `shares_diluted_wavg` (D-M04-2).
- **Market cap:** `financials/distress.py` `market_value()` = cover shares × raw close (`shares.close_on` on `price_bar`, 5-day tolerance; split guard `shares.split_note`; Tiingo, grade A per D-M04-82, internal use only S68).
- **Debt and cash:** `financials/debt.py` `_Book.point()` (Part 4a), reused; an absent current-debt tag counts as none and is named, as in M04.
- **Stage, tags:** `company_stage` + `stage.confirmed()` (Part 1c; 7 confirmed, all mature; 8 open: BA, INFQ, INTC, MU, NVDA, SPCX, TSLA, RIVN); `config/company_models.toml` (MSTR `asset_treasury`, ETV `fund`, INFQ `spac_shell` before 2026-02-13).
- **Peers:** `peer_group` / `peer_member` + `peers.confirmed_peers()` (7 sets still open).
- **Reused M04 rows, not rebuilt:** `filing_status`, `survival_gate`, `net_debt_ebitda`, `overreaction_gap`, `normalized_ep_cur` (NEP, D-M04-54, -83; 8a, not built).
- **Other:** `signals.write_signal`; Alpha Vantage client and shared `fetch_log` budget, 25/day, 20 scheduled (`calls/alpha_vantage.py`, transcripts only today; D-M02-20).

**Missing (gap · request cost):** analyst estimates (`EARNINGS_ESTIMATES`) · new gap, ≈ 16 Alpha Vantage calls a week (Q08.6) · `MinorityInterest` unmapped · 0 requests for covered companies (tag already in `fact`); peers keep it only after their next companyfacts fetch · operating leases · left out of EV by design · prices for peers outside the core/promoted/tracked tiers · new gap, 1 Tiingo request per symbol plus a daily refresh (Q08.2b) · options · DS5 · short interest · DS18 proposed in the M07 brief (Q07.8) · FRED DGS10 · deferred.

## MVP signals
`module_id` M08, keyed by `cik` (D-M04-74), one row per timeframe; `value` for numbers, `value_text` for bands and codes (`value` NULL when there is no number); missing = both empty and `method` "missing: <reason>", never zero (D-M04-9). `as_of` = the close date used. ✓ = may carry weight once D13 weights exist; info = weight 0.

| Signal | value / value_text | Meaning | Inputs | MY | PT | ST | Grade |
|---|---|---|---|---|---|---|---|
| `valuation_multiple` | multiple; text when no value: `not_meaningful`, `stage_unconfirmed`, `fair_value_earnings`, `not_applicable` | Stage headline: intro/growth EV/S (EV/GP beside it); mature P/E TTM and EV/EBIT; shake-out and cyclical (flag overrides stage) EV ÷ NEP; decline EV/EBIT and P/B; MSTR mNAV. Every other measure in `method` (D10); "EV incomplete" there when the value is P/S | facts_as_of, market_value, debt book, stage, tags | ✓ | ✓ | info | A |
| `valuation_pctile` | 0–100 | Headline's percentile in its own quarterly history (≥ 20 points, first-filed values, recomputed each run); peer percentile in `method` when ≥ 5 confirmed peers have stored prices | same, at each past quarter-end | ✓ | ✓ | info | A |
| `peg` | ratio; text band `≤1` / `1–2` / `>2` (outline PEG item 2) or a reason code (below) | R6 PEG; trailing 3-year GAAP EPS CAGR in `method`, never substituted. R6's sales fallback = the EV/S row and its percentile | estimate snapshot, close, facts | ✓ | ✓ | info | B (vendor growth) |
| `est_revision` | % (FY1 30-day revision); text up / flat / down | R15 direction. `method`: FY1/FY2 30- and 90-day revisions, breadth (up − down) ÷ count, dispersion (high − low) ÷ \|avg\| when count ≥ 3, the count, "vendor basis" | estimate snapshot | ✓ low (M01) | ✓ | ✓ | B |

PEG reason codes, first failing check wins, all failing checks in `method` (order a starting value): `fair_value_earnings`, `eps_nonpositive`, `cyclical`, `growth_missing`, `base_nonpositive`, `growth_nonpositive`, `growth_above_cap`.

## Worked example
Closes from the Yahoo chart API (S-new-M08-43, other); at build they come from `price_bar` (pack known gap 8). SEC figures from companyconcept, as in the pack.

**Micron across the cycle** (cyclical flag fires: operating margin −37.0% in FY23 to +31.5% in FY22, ≥ 30 pp):

| 10-K filed | Close | FY EPS | Trailing P/E | PEG code | Price 1 yr later |
|---|---|---|---|---|---|
| 2022-10-07 | $52.91 | 7.75 | 6.8× (peak: "inverts at cycle extremes") | `cyclical` | +32% |
| 2023-10-06 | $69.96 | −5.34 | `not_meaningful` | `eps_nonpositive` | +46% |
| 2024-10-04 | $102.25 | 0.70 | 146.1× | `cyclical` (+ `base_nonpositive` in method) | +84% |
| 2025-10-03 | $187.83 | 7.59 | 24.7× | `cyclical` | $1,029 (2026-10-09) |

In the engine these past rows read `growth_missing` (consensus history starts with the first snapshot); the codes show the R6 logic only.
- **Headline on 2024-10-04.** Pack window FY2019–24: cycle-average operating margin = 21,923 ÷ 143,955 = 15.2%; × FY2024 revenue $25.111B → NEP ≈ $3.82B; headline = EV ÷ $3.82B (EV computed at build). The engine uses M04's trough-to-trough window (D-M04-83), so the figure may differ.
- **Normalized P/E, same date** (cycle-average EPS $2.688) = 38.0× vs 146× trailing; shown in `method`.

**Other companies:**
- **NVDA** (stage open; mature if confirmed): TTM EPS 7.91 at $229.28 → P/E ≈ 29.0×. H1 FY27 EPS growth +164% > 50% cap → PEG `growth_above_cap` (uncapped 0.18 in `method`, Q08.5a).
- **INFQ** (losses): 225,357,052 shares × $11.04 = $2.488B market cap; TTM revenue $41.081M → P/S 60.6× ("EV incomplete": debt and cash not fetched in the pack). Own percentile missing (< 20 quarters).

**Estimates.** Alpha Vantage demo, IBM, 2026-10-12, real:

| Horizon | Avg EPS | 90 d ago | Rev. 90 d | Rev. 30 d | Up/down 30 d | Count | Dispersion |
|---|---|---|---|---|---|---|---|
| FY2026 | 12.3121 | 12.4709 | −1.27% | −0.07% | 0 / 1 | 23 | 4.5% |
| FY2027 | 13.1512 | 13.4736 | −2.39% | −0.09% | 11 / 10 (+0.04) | 23 | 11.8% |

- **`est_revision`** = −0.07% (FY1, 30 days) → "flat" (flat band set at build, e.g. \|x\| < 0.5%, illus.).
- **PEG growth** g = 13.1512 ÷ 12.3121 − 1 = 6.8%; with a forward P/E of 20× (illus.), PEG = 2.9, band `>2`.

## Cases the rules must handle
1. Profitable, long history (MSFT): every measure; percentile scored.
2. Losses (INFQ): P/E, EV/EBIT `not_meaningful` in `method`; headline EV/S, EV/GP beside.
3. Any denominator ≤ 0 (gross profit, equity for P/B) or EV ≤ 0 (net cash above market cap): that measure `not_meaningful` (D-SRCH-15).
4. Debt or cash untagged: value = P/S, `method` "EV incomplete"; finance leases in the debt tag labelled; operating leases excluded ("EV ex operating leases").
5. < 20 quarterly points (SPCX, listed 2026-06-12; INFQ): `valuation_pctile` missing.
6. < 5 priced confirmed peers or non-SEC peers (SK hynix): peer percentile "missing: n priced peers" in `method`.
7. Stage unconfirmed (8 open, D-M04-7): value NULL, text `stage_unconfirmed`, all measures in `method`, every timeframe info. The cyclical flag overrides this (MU).
8. Cyclical flag: headline EV ÷ NEP; trailing P/E "inverts at cycle extremes"; PEG `cyclical`. Before M04 8a: "missing: NEP awaits M04 8a", EV/S in `method`.
9. MSTR (`asset_treasury`): mNAV, "crypto exposure" (scope S1); P/E, PEG `fair_value_earnings`. ETV (`fund`): `not_applicable`.
10. INFQ: shell periods excluded by the de-SPAC boundary; recast FY2025 (−66.9M vs −32.2M) → one series per TTM, break flagged.
11. GFS (20-F): quarters from XBRL 6-K where filed (M04 1a reads them); else annual, "as of FY".
12. Split between share date and close (NVDA 2024): split guard (`split_note`).
13. No close within 5 days of d: missing. Filing stale or overdue: "as of <period>" plus M04 `filing_status`.
14. Estimates: count < 3 → no dispersion; \|avg\| < $0.10 or a sign change → revision `not_meaningful`; null vendor counts (null in every demo row) → missing, never zero.
15. No coverage (INFQ, SPCX, GFS unprobed): `growth_missing`; low coverage shown (outline Analysts item 4).
16. Non-calendar fiscal years (MU, NVDA, MSFT): map by vendor period-end `date`.
17. Snapshot missed (budget, PC off): missing, in the run report.
18. ≤ 30 days before a report: "walk-down window" (S-new-M08-16).
19. D9: vendor consensus is non-GAAP → "vendor basis" label; a percentile across a structural change (AI ramp) reads "expensive" for years → beside M04 trends, never a sell signal (D16); `adj_close` distorts past market caps → raw close only.
20. D9: cheap is not a buy (outline TA item 1): low percentile with a gate fail or (after 8a) a CvD decline → "value-trap risk".
21. D9: peer percentile inherits peer quality (D19, S163): shown, not scored.

## Deferred to the tuning phase
- R1: earnings yield vs DGS10 (new FRED fetch); valuation ceiling (M01 rule 4, needs M11 positions); operating leases in EV (after the first live log).
- R2: cyclical review queue (toml override instead); own normalization (one NEP in M04, D-M04-54, -83); `cvd_state` notes once 8a lands.
- R3 Finnhub `rec_change_3m`, `eps_surprise`, guidance-vs-estimate notes: more calls plus a review kind.
- R3 revenue revisions (outline Analysts item 3), history past 90 days: need weeks of own snapshots (every vendor field stored from day one).
- Outline Analysts item 5 crowded consensus: M02 theme crowding and the analyst count stand in.
- R4 short interest, FINRA short volume: M07's Q07.8 (pack known gap 2: Massive docs vs pricing conflict).
- R5 options skew and IV: DS5 / Q5 with M12. R6 news attention and tone: store began 2026-10-12 (< 26 weeks), Gemini needs 100 blind labels; S6.3 weights wait for D13 weights.

## Questions for the owner
- **Q08.1 Headline per stage.**
  - a) Route by M04's confirmed stage (pack S1.1 table); the cyclical flag overrides; unconfirmed → `stage_unconfirmed`, all measures shown, not counted. Owner override per company in `config/valuation.toml`.
  - b) One fixed pair (EV/S and P/E) for everyone.
  - c) The owner sets each company.
  - Why (a): reuses M04's stage and its review (D-M04-7, -12); earnings price best where positive (S-new-M08-1). Today 7 companies (all mature) route; clearing the 8 open `m04_stage` items routes the rest.
- **Q08.2 Comparison frame.**
  - a) Score the own-history percentile (≥ 20 quarters). Show the peer percentile only where ≥ 5 confirmed peers already have stored prices. No new price fetch.
  - b) Also backfill peer prices from Tiingo: an owner-run batch of 1 request per peer symbol at ≤ 40 an hour (up to ~2 h), then daily refresh; counts toward Tiingo's 500 symbols a month (S68). Then score on peers.
  - c) Own history only.
  - Why (a): zero new requests, and 7 peer sets are still open; peers stay visible where they exist (S163, DS8 limits).
- **Q08.3 Cyclicals (R6 "flag cyclicals").**
  - a) Computed flag: an EPS sign change in 10 fiscal years, or an operating-margin range ≥ 30 pp; owner override in toml. Cyclical headline = EV ÷ M04 8a's NEP on current revenue, read from 8a's computation for every flagged company (8a's signal encoding stays as is, D-M04-9).
  - b) M08 computes its own normalized EPS and EBIT.
  - c) Flag only; no normalized multiple in the MVP.
  - Why (a): one NEP definition and window (D-M04-54, -83). Micron's 146× trailing vs 38× normalized shows the trailing number misleads (S-new-M08-9).
- **Q08.4 PEG basis.**
  - a) Forward P/E (close ÷ FY1 consensus) ÷ FY1→FY2 consensus growth, all on the vendor basis, labelled; trailing 3-year GAAP CAGR beside it.
  - b) TTM GAAP P/E ÷ consensus growth (mixed bases, labelled).
  - c) TTM GAAP P/E ÷ trailing 3-year CAGR (grade A, backward-looking).
  - Why (a): one basis, and the outline asks for *expected* EPS growth; forward earnings price best (S-new-M08-1).
- **Q08.5 PEG growth cap.**
  - a) PEG scored only when 0 < g ≤ 50%; above that, text `growth_above_cap`, the uncapped PEG in `method` (not scored) and EV/S shown.
  - b) No cap.
  - c) The owner sets it per company.
  - Why (a): PEG treats short-run growth as long-run growth and fails worst on ramps (S-new-M08-6). Outline PEG item 1 wants PEG for S-curve names, so the uncapped figure stays visible (D10).
- **Q08.6 Estimate source and budget.**
  - a) Alpha Vantage `EARNINGS_ESTIMATES` once a week per company (≈ 16 calls a week: core + promoted, ETV excluded; ≤ 3 a day in the logon run, transcripts first), stored in `estimate_snapshot`.
  - b) Fetch only on request.
  - c) No estimates in the MVP: no `est_revision`, and PEG falls back to Q08.4c.
  - Why (a): the only free source of revisions and dispersion (R15, S-new-M08-19); each call carries the 7/30/60/90-day-ago averages, so revisions work from the first snapshot.
- **Q08.7 MSTR.**
  - a) mNAV = market cap ÷ `CryptoAssetFairValue`, labelled "crypto exposure"; P/E and PEG `fair_value_earnings`.
  - b) Leave MSTR out (`not_applicable`).
  - c) Ordinary measures.
  - Why (a): its EPS moves with bitcoin under ASU 2023-08 (S-new-M08-42) and the tag is already mapped; matches M04's `asset_treasury` (D-M04-8).

## Build parts
**Part 1 — Valuation core (0 network requests)**
- **Goal:** `valuation_multiple` and `valuation_pctile` for core and promoted companies; the cyclical flag; MSTR mode.
- **Code:** new `src/engine/valuation/` (measures, as-of points, percentile, cyclical, views), reusing the functions above (`debt._Book` made public). `MinorityInterest` added to `EXTRA_CONCEPTS` (read from stored `fact`; no parser bump). The step joins the refresh's local pass after prices.
- **Tables:** none expected (quarter-end history recomputed each run from `fact` and `price_bar`); a migration (number assigned after M04's 0038/0039) only if the mock-up needs a history cache.
- **Config:** `config/valuation.toml` (headline overrides, cyclical override). **Review kinds:** none.
- **UI:** new M08 tab "Valuation" (headline, all measures, percentile, reasons). Mock-up first with MU and INFQ (D-UI-4), on scratch data on port 8799.
- **Live check:** `uv run python scripts/run_valuation.py value --no-sec`. 0 SEC or API requests, under 1 minute. The owner checks the MU 2022–25 rows against stored closes, NVDA ≈ 29×, INFQ P/S, MSTR mNAV and GFS quarterly vs annual.
- **Fixtures:** MU 10-K dates with the pack's closes as fixture prices, NVDA split, INFQ recast, MSTR, negative equity, EV ≤ 0. **Depends on:** M04 1a–4a (built); 8a NEP soft (case 8).

**Part 2 — Estimates and PEG**
- **Goal:** `estimate_snapshot` (migration TBD: cik, ticker, horizon, period_end, every vendor field, fetched_at), the weekly rotation inside the Alpha Vantage budget, `est_revision` and `peg`.
- **Code:** `calls/alpha_vantage.py` gains `EARNINGS_ESTIMATES` (key never logged); `valuation/estimates.py`, `valuation/peg.py`.
- **Review kinds:** none. **UI:** an "Estimates" block on the M08 tab.
- **Live check:** `uv run python scripts/run_valuation.py estimates --probe INFQ,SPCX,GFS,MU,MSFT`. 5 Alpha Vantage requests, 15 s apart, about 1.5 minutes. The owner checks coverage, fiscal mapping and null fields.
- **Fixtures:** the IBM demo response (byte-exact), a no-coverage reply, a sign-change case. **Depends on:** Part 1; M02's Alpha Vantage client and budget (D-M02-20).

## Open risks
- **Coverage.** Alpha Vantage coverage of INFQ, SPCX and GFS is unknown, and its "not Premium" status was seen only on 2026-10-12 (S-new-M08-19). If it changes, PEG falls back to Q08.4c.
- **Budget clash.** In earnings weeks transcripts can use the whole 20-call budget; snapshots are skipped and reported missing.
- **Routing and peers.** Until the 8 open stages are confirmed, MU, NVDA, INFQ and five others carry `stage_unconfirmed` (weight 0) unless flagged cyclical; few confirmed peers have prices (Q08.2).
- **Unchecked filings data.** INFQ's predecessor series, MSTR's `CryptoAssetFairValue` coverage by quarter and GFS's 6-K XBRL coverage are unverified (pack known gaps 5 and 9). The Part 1 live log settles them.
- **Licences.** Tiingo and Alpha Vantage data are personal use only (S68, DS1); M08 output is not shareable.

## Check notes (2026-10-13)
- **Outline fit.** Analysts item 5 (crowded consensus) was silently dropped → added to departures and Deferred, with M02's crowding flag as stand-in. Analysts item 3 revenue revisions now cite the outline in Deferred. Q08.5's 50% cap excluded exactly the S-curve ramps outline PEG item 1 is about → the uncapped PEG now stays in `method` (Q08.5a). The "items 1–3" scope was widened to 1–4 (case 15 serves item 4).
- **Binding decisions / overlap.** M01 gives analysts "low" MY weight, not zero → `est_revision` MY changed from info to "✓ low". Short interest is outline Ownership item 4 (M07, D15) and is already asked as Q07.8 in the M07 brief → Q08.8 removed to avoid two answers to one question; the brief now points to Q07.8 (and DS18 proposed there). R6's sales fallback named explicitly (EV/S row). Q08.3a asked 8a to write a NEP value beside its "not used" text, which breaks D-M04-9's value_text-with-NULL-value encoding → now reads NEP from 8a's computation. NEP window marked as D-M04-83 trough-to-trough (the FY2019–24 figure is the pack's window). M04 `overreaction_gap`, `net_debt_ebitda`, `survival_gate` listed as reused, not rebuilt.
- **Data reality.** All named functions, tables and concepts exist (`market_value`, `_Book.point`, `close_on`, `split_note`, `stage.confirmed`, `confirmed_peers`, `write_signal`, `facts_as_of`, `company_stage`, `filing_status`, `peer_group`/`peer_member`, `price_bar`, `fetch_log`, `signal` with `cik`/`value_text`). Fixed: GFS was called a "6-K without XBRL" new gap, but M04 1a reads GFS quarters from XBRL 6-K (M04_BUILD_LOG form-filter row) → case 11 and the Missing list corrected. `MinorityInterest` is in `fact` for covered companies only; peers keep only mapped tags (peer_facts) → noted. Request costs added to every gap. Q08.2b used 50/h; the batch budget is 40/h plus a 500-symbols-a-month cap → corrected. Estimate calls 15 → ≈ 16 a week (15 watchlist equities ex-ETV + RIVN). Stage facts added (7 confirmed, all mature; 8 open) and a routing-coverage risk.
- **Numbers and sources.** All figures recomputed (MU P/Es, returns, NEP 15.2%/$3.82B, 38.0×, NVDA 29.0×, INFQ $2.488B/60.6×, IBM revisions, dispersion, PEG 2.9) and match the pack. "L9" does not exist in LESSONS.md → replaced by pack known gap 8. "M04 S-new-2" is now S163 (M04 pack map) → replaced. The MU PEG column mixed reason orders (2022 `cyclical` but 2024 `base_nonpositive`) and could not be computed historically → a fixed reason order is stated, the 2024 row follows it, and a note says past rows read `growth_missing`. "S1" in Q08.7 clarified as the scope decision.
- **MVP discipline / D13.** 4 signals, 7 questions, 2 parts, live checks < 2 min: kept. Added: `cik` key, `as_of` rule, `value_text` for bands and codes with `value` NULL when there is no number ("EV incomplete" moved to `method`, since the P/S fallback carries a value; `ev_incomplete` dropped as a no-value code), `stage_unconfirmed` rows as value NULL with every timeframe info (D-M04-7). Part 1 "depends on case 13" pointed at ETV → case 8. Fixtures no longer claim to equal stored Tiingo closes (Claude cannot read `data\`). Cases list merged from 31 to 21 with no case dropped. The body is about 17k characters, above the 15k target, because of the added gap costs and D13 detail.
