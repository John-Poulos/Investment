# M07 Ownership & insiders — MVP brief
**Decided 2026-10-13 → docs/M07_OWNERSHIP.md** (D-M07-1…8; Q07.1a–Q07.8a, Q07.8 restored by MVP_PLAN QP.3). Kept as the sitting record.
Updated 2026-10-13 · Source: docs/M07_DESIGN_PACK.md (research) · Status: for owner decision (one sitting) · Outputs are research signals, not advice.

## Purpose in one paragraph
Turn the Form 4s the engine already stores, plus the 13F filings of a few managers the owner names, into D13 signals that answer "are insiders buying with their own money, are they selling outside their plans, and is the smart money adding?" It serves the outline's "Ownership and Insiders" items 1–3 and its CRWV example (shares, $ and float share over a window). Binding: **R7** (weight opportunistic buys; routine/10b5-1 sales noise unless abnormal), **R13** (raw Form 4 totals), **R16** (Form 4, 13D/G in all timeframes; 13F lagged), **R22** ($, % of stake, % of float/volume; G/A/M/F out of $ totals), D-SEC-10 (plan per row), **D-M04-2** (float = EntityPublicFloat ÷ close, "implied"), M01 rule 6 and "ownership medium" in MY. Sale items are warnings only (D16). **Where this departs from the outline:** item 4 (short interest) is not in the M07 pack; the M08 pack researched it (Round 4: FINRA, Massive) and asks it once as **Q08.8**, so M07 does not ask it again. Item 1's "quality, not just %" is covered only through the owner's followed managers (all-holder 13F deferred, R5). Item 2's "CEO of equity" is listed beside Druckenmiller, so it reads as a manager's name, not the company CEO's stake that the pack's 5.1a guessed (Q07.7; DESIGN Q3). R16's 13D/G half is met only if Q07.6b/c is chosen.

## Data already stored that the MVP uses
| Need | Stored in | Code | Gap |
|---|---|---|---|
| Form 4 rows: code, shares, price, shares_after, D/I, role, footnotes, is_10b5_1, plan_basis | `insider_txn` (0001, 0005) | `sec/insiders.py` (form4-1), `transactions()` | Back to ~2023-10 only (`form4_years = 3`) → Q07.1 |
| Form header: 4 vs 4/A, aff_10b5_1, all joint owners | `form4_doc` (0005) | same | No 4/A replacement rule yet |
| Holding lines without a transaction (Huang's 8 indirect lines) | not stored; raw XML is in the HTTP cache (`DOC_TTL_S` 10 years) | re-parse as form4-2 | new table, 0 SEC requests expected |
| Cover share count, implied float, close, splits | M04 signals `shares_cover`, `implied_float_shares` (reused, not rebuilt); `fact` (0001), `cover_shares` (0029), `price_bar` (0012) | `financials/shares.py` `cover_counts`, `implied_float`, `close_on`, `splits_after` (M04 Part 1a) | GFS (20-F) has no float → "float unknown" |
| 20-day volume | `price_bar.volume` (raw) | M04 split guard | — |
| 13F reader, CUSIP → company map | `fin_13f`, `fin_holding`, `fin_issuer_map` (0023) | `financing/thirteenf.py` (`read_filing`, `store_rows`, `current`), `issuers.py` (`resolve`) | Today only 13Fs filed *by* AMZN, GOOG, INTC, NVDA; a manager's filing list is not in `filing` → DS11 extension (followed managers) |
| Signal store | `signal` (0029: cik key, value_text) | `signals.write_signal` (upsert on cik, module, signal, timeframe, as_of) | — |
| Short interest | none | — | M08's gap (Q08.8), not M07's |

## MVP signals
| Signal | value / value_text | Meaning | Inputs | MY | PT | ST | Grade |
|---|---|---|---|---|---|---|---|
| `insider_buy` | $ of open-market P rows / `opportunistic`, `routine`, `unclassified`, `purchase_from_issuer` | An insider bought with own money (R7) | P rows of one form; CMP class (owner, issuer, year); % of stake after, % of cover count; cluster count (distinct owner CIKs buying in 90 days) | ✓ + rule 6 alert (opportunistic); alert, no score (unclassified) | info | info + alert | A |
| `insider_sale` | $ of S rows only / `plan`, `plan_na`, `non_plan_routine`, `non_plan_opportunistic`, `non_plan_unclassified` | R22 sale card; warning only for non-plan, non-routine sales | S rows of one form; excluded F/M/A/G rows listed "not in total"; % of stake before, % of cover count, % of implied float, % of 20-day ADV | warning (Q07.3); info for plan/routine | info | info | A |
| `insider_net_flow` | net $ = open-market P − non-plan S / `net_buy`, `net_sell`, `plan_only`, `none` | Outline item 3: buying should exceed selling, with 10b5-1 sales shown apart | All P/S in the window (MY 12 months, PT 3 months, ST 30 days); gross S shares and $ (the outline's CRWV figure) and plan / `plan_na` sales shown beside, not in net; shares as % of cover count and implied float; insider count | info (Q07.5) | info | info | A |
| `followed_manager_13f` | Δ shares / `new`, `add`, `cut`, `exit`, `hold` | Outline item 2: buys by managers the owner trusts (soft, lagged) | Followed manager's 13F-HR, summed by CUSIP, our companies only; Δ% of shares outstanding; period and filing date | ✓ (soft) | info | info (weight 0) | A |

All rows: keyed by `cik` (ticker for display, D-M04-74), `module_id = "M07"`, numbers in `value` and classes in `value_text` (D-M04-9), `source_ref` = newest accession "+N" with every form in `method`, one row per timeframe, as_of = filing date (the alert fires on the filing day, not the trade day). Missing inputs give a "missing: …" row, never 0. Event signals leave scoring after the profile window and stay visible (D10). PT and ST stay info until M01 designs those columns (M01 open question).

**One row per company and filing day.** `write_signal` upserts on (cik, module, signal, timeframe, as_of), so two Form 4s filed for one issuer on one day (common at AAPL vesting dates), or two followed managers' 13Fs on the 45-day deadline, would overwrite each other. Rule: same-day forms aggregate into one row (value = summed $ or Δ shares; value_text = the strongest class present, in the order opportunistic, unclassified, routine, `purchase_from_issuer` for buys and non-plan opportunistic → plan for sales; `mixed` for 13F directions). Per-form cards are built by the Insiders tab view from the stored rows, not from `signal`. `insider_net_flow` is written once per timeframe (its window differs); a window with no P/S gives value_text `none` with no value, and a window that starts before the stored Form 4 history gives "missing: history starts <date>".

## Worked example (real figures from the pack, S-new-M07-18, and D-SEC-10)
**Huang, NVDA, Form 4 0001045810-25-000143 → `insider_sale`.**
- 7 S rows on 06-20 and 06-23: 100,000 shares, $14,403,585 (average $144.04). Footnote F3 says the sales were under a plan → `plan`, info, no alert.
- F row on 06-18: 40,163 shares at $144.12 = $5,788,292, listed "not in total" (it would add 40%).
- % of stake: 100,000 / 75,773,225 = 0.13% on the direct line alone; 100,000 / 859,148,625 = 0.012% over all 9 lines. form4-2 is needed, or the figure is 11× too high (Q07.4).
- % of shares outstanding: 100,000 / 24,400,000,000 (rounded cover count) ≈ 0.0004%. ADV share: illus. (computed from `price_bar` at build).

**Musk, TSLA, Form 4 0001104659-25-089693 → `insider_buy`.**
- 25 P rows on 2025-09-12 through his trust: 2,568,732 shares, about $999.96M; `aff10b5One` = 0.
- 0.50% of his stake after the buy; 2,568,732 / 3,225,448,889 = 0.080% of the cover count (2025-07-17).
- A 2025 trade needs P/S rows in 2022, 2023 and 2024, which are not stored even under Q07.1a → `unclassified` → alert in all timeframes, no score (Q07.2a).

**Tan, INTC, Form 4 0001127602-25-010360.** Code A, 1,043,406 shares at $23.96 ≈ $25.0M, with a footnote citing the offer letter (8-K Item 5.02) → `purchase_from_issuer`: shown, not scored.

**AAPL, 3 stored years (D-SEC-10 live re-run).** 60 Form 4s, 170 rows. Of 48 sales, 43 are plan by row footnote and 5 are non-plan. `insider_net_flow` shows the 43 plan sales beside the net. Only the 5 non-plan sales can enter it, and under Q07.3a they warn only if their insider is opportunistic, or unclassified and selling ≥ 10% of stake. $ amounts: illus. until the build's report.

**Berkshire → AAPL, 13F for 2024-06-30, filed 2024-08-14 → `followed_manager_13f` = `cut`.**
- 789,368,450 → 400,000,000 shares (−49.3%); 5.15% → 2.63% of shares outstanding.
- The method states "lagged: quarter ended 2024-06-30, filed 45 days later".

## Cases the rules must handle
1. P/S rows in all 3 prior calendar years with a common month → routine. Without a common month → opportunistic (CMP, S09).
2. A missing prior year (new insider, SPCX listing, INFQ post-SPAC, history not stored) → `unclassified`, never defaulted. The years used are stored.
3. Insiders whose history is only A/M/F/G/J/K/D/W/C/X/U rows → never classified, never in $ totals.
4. P bought from the issuer, a private placement, or A with a price and a contract footnote → `purchase_from_issuer`, not scored, not in net flow.
5. Several trusts or a joint filing for one person → one owner CIK. Rows carry the first owner only (D-SEC-10); clusters count distinct CIKs.
6. Insider of two issuers, or also a 10% owner → class per (owner, issuer).
7. Form 4/A → replaces the original, matched by (owner, date, shares). No repeat alert.
8. Many S rows across days → summed per form. Mixed S + F → F listed "not in total".
9. Plan by row footnote → `plan`. Checkbox set, row not identified → `plan_na` (shown apart, not in net).
10. Gift (G) at price 0 → out of totals and shown as a row only (gift flags deferred).
11. Stake: all non-derivative lines on the form (form4-2). Derivatives shown apart. Only a Form 3 on file → stake missing.
12. Cover count rounded (NVDA) or exact (TSLA) → source and date in the method. Multi-class → M04's class-summed R1 count.
13. Float: implied (D-M04-2). 20-F filer (GFS) or new listing → "float unknown", never 0.
14. Split inside the ADV window → raw volume plus `splits_after` guard. No bars → ADV share missing.
15. Cluster: ≥ 3 distinct opportunistic buyers in 90 days (MY) → attribute on `insider_buy`, not a separate signal.
16. 13F: several rows per CUSIP summed; put/call rows kept apart; thousands before 2023-01-03 (LESSONS); amendments replace.
17. 13F rows of companies that are not ours → not stored and not queued. This needs a new filter before `thirteenf.store_rows`, which today stores every row and turns unresolved ones into M02 `m02_13f_issuer` review items. Our CUSIP unresolved → held once, with the CUSIP shown.
18. A followed manager with no 13F for a quarter → missing for that quarter, never "exit".

**Failure modes (D9):** short history → everyone looks opportunistic (guard: `unclassified`) · predictability sits mainly in small firms and 1986–2014 samples (S-new-M07-1) → upper bounds, MY only · direct-line stake 11× too high → form4-2 · mega-cap net flow is nearly always selling (stock pay) → info, plan apart · strategic plan timing (S-new-M07-6) → "plan = noise" is the MVP's known blind spot · 13F stale and long-only → "lagged", 0 in ST · copying managers adds little after costs (S-new-M07-15) → soft weight · a misread footnote flips plan status → `plan_basis` on every card.

## Deferred to the tuning phase
- R1: Ali–Hirshleifer definition (S-new-M07-5), role multiplier (S-new-M07-4), Data Sets from 2006 (DS6) — CMP first; single study; backtest use (unless Q07.1c).
- R2: plan registry and cooling-off (Item 408 finder + review items), Form 144, gift/hedge/late flags — new finders, review kinds, SEC holiday calendar.
- R3: economic stake (options, RSUs), affiliate float (D-M04-2's implied float stands), totals by role and month (S3.3).
- R4: 13D/13G about our companies, crossings, lockups (SPCX, INFQ) — unless Q07.6b/c.
- R5: all-holder 13F Data Sets (~96 MB a quarter), passive/active split — named managers first.
- R6: decay, backtest calibration, PT/ST weights — needs use and M01's PT/ST design.
- Short interest (outline item 4): owned by M08 (pack Round 4) and decided once under Q08.8; M07 shows it on the Insiders tab later if M08 builds it.
- R16's 13D/G half: until R4 (or Q07.6b/c), 13D/G about our companies are only listed in `fin_schedule` headers; M02's Money flow tab shows the ones whose XML was read.

## Questions for the owner
**Q07.1 History for the CMP class** (a 2026 trade needs P/S rows in 2023–2025; storage starts ~2023-10)
- a) *Recommended.* Set `form4_years = 4` and run one owner-run fetch of the missing year first (back to ~2022-10, the window that setting keeps; the filing lists are already stored, since `sync_filings` reads every submissions page). Why: classes work now, and stay complete each 1 January (S09). About 12 months of Form 4s, est. a few hundred requests and 1–3 minutes; the dry run prints the exact count first. Without the owner run, the next logon refresh would fetch the gap itself (`sync_insiders` takes the configured window).
- b) Keep 3 years. Most insiders read `unclassified` until 2027-01-01.
- c) Data Sets backfill from 2006 (DS6, ~83 ZIPs).

**Q07.2 Buys by insiders CMP cannot classify**
- a) *Recommended.* Alert in every timeframe, no score. Why: a default would score noise, and the alert keeps every own-money buy visible (pack 1.1a, R7).
- b) Score them as opportunistic.
- c) Hide them until history exists.

**Q07.3 Non-plan sales**
- a) *Recommended.* MY warning for `non_plan_opportunistic`. `non_plan_unclassified` warns only at ≥ 10% of stake. Routine and plan sales are info. Why: opportunistic sales carried −78 bps a month (S09); large-% sales are the ones that predict (S-new-M07-7).
- b) Warn only at ≥ 10% of stake, whatever the class.
- c) Info only.

**Q07.4 Stake denominator**
- a) *Recommended.* All non-derivative lines on the form (form4-2 re-parse from the cache, 0 requests expected); derivatives apart. Why: the direct line alone overstates Huang's sale 11× (pack 3.1a).
- b) `shares_after` of the traded lines only, labelled "traded lines".

**Q07.5 Net flow**
- a) *Recommended.* Net = open-market P − non-plan S. Plan and `plan_na` sales shown beside, not netted. Info in all timeframes. Why: outline item 3 asks for the balance "with context given to scheduled 10b5-1 sales"; R7 makes plan sales noise.
- b) P − all S, info.
- c) Drop it; the per-form cards are enough.

**Q07.6 Fourth signal**
- a) *Recommended.* `followed_manager_13f` for owner-named managers. Why: outline items 1–2 name smart-money 13Fs. It reuses `thirteenf.py` at about 25–40 requests per manager once (submissions pages, then index, cover and table for 8 quarters), then about 4 per new 13F-HR.
- b) 13D/13G about our companies (meets R16's 13D/G half; the headers are stored, est. a few hundred XML reads once).
- c) Both, as two build parts.
- d) Neither in the MVP.

**Q07.7 Followed managers and "CEO of equity"** (DESIGN Q3). The outline reads: "Look at 13F filings with buys from the smart money as a soft signal - CEO of equity, Stanley Druckenmiller, etc."
- a) *Recommended.* Start with Duquesne Family Office (Druckenmiller) and Berkshire Hathaway in an owner-edited `config/m07_managers.toml`. Please write the name meant by "CEO of equity" and it is added (a guess only: "CEO of Fidelity", Abigail Johnson of FMR, who appears in the pack's GFS 13G example). Why: the outline lists it beside Druckenmiller, so it reads as a manager.
- b) Give the full list before the build.
- c) It meant the company CEO's own stake → shown on the Form 4 cards; no 13F for it.

## Build parts
**Part 1: Insider signals (Form 4)**
- **Goal:** `insider_buy`, `insider_sale` and `insider_net_flow`, with R22 cards.
- **Code:** `sec/insiders.py` form4-2 (holding lines; the `PARSER_VERSION` bump makes `sync_insiders` re-parse every Form 4 from the cache, so the owner script runs it before the first logon refresh on the new code, or the refresh does it and fetches any cache miss); new package `ownership/`: `classes.py` (CMP), `cards.py` (stake, cover, implied float, ADV via `financials/shares.py`), `step.py` (local pass after `prices_step`, 0 SEC requests), `views.py`; owner script `scripts/run_ownership.py insiders [--history] [--no-sec]`.
- **Tables:** migration number in merge order (M04 4b-lite holds 0038, 8a 0039; no gaps): `form4_holding(accession, line, table_kind, title, shares, direct_indirect, nature, footnotes)`, `insider_class(owner_cik, issuer_cik, year, class, years_used, months_seen)`, and a 4/A link column.
- **Review kinds:** none.
- **UI:** Insiders tab with buy and sale cards, a net-flow strip per window, and class and plan columns; one Overview row (latest buy, net flow MY).
- **Live check:** `run_ownership.py insiders --no-sec` (cache re-parse; any cache miss is counted). If Q07.1a, then `--history` (est. a few hundred requests, 1–3 minutes).
- **Fixtures:** synthetic Form 4 XML in the layout of Huang (9 lines, F row, footnote F3), Musk (25 P rows, trust) and Tan (code A, offer-letter footnote); a 4/A pair; the illus. Director X / CFO Y / CEO Z histories.
- **Depends on:** M04 Part 1a (built). Not on 4b-lite or 8a. M01 rule 6 reads `insider_buy`; alerts go to the existing end-of-run box.

**Part 2: Followed managers (if Q07.6a/c)**
- **Goal:** `followed_manager_13f`.
- **Code:** `config/m07_managers.toml`; `ownership/managers.py` syncs each manager's filing list (`sync_filings`, so `thirteenf.due` finds its 13F-HRs) and calls `thirteenf.read_filing` with a new keep-filter (rows that `issuers.resolve` maps to a watchlist or tracked company; others not stored, so `financing/step.issuer_items` never queues them); the refresh SEC part runs only when the daily index shows a new 13F-HR from a followed manager.
- **Tables:** reuses `fin_13f` and `fin_holding` (source 13F, filer = manager); migration only if a manager list table is needed (TBD).
- **UI:** "Followed managers (lagged)" panel on the Insiders tab.
- **Live check:** `run_ownership.py managers`: about 25–40 requests per manager (submissions pages, then index, cover and table per filing for 8 quarters), under a minute for 2–3 managers at the 5/s pacing.
- **Fixtures:** a Berkshire-style information table with split rows per CUSIP and a pre-2023 thousands filing.

## Open risks
- Mega-cap watchlist: open-market buys are rare (Musk 2025), so `insider_buy` seldom fires; most activity is plan selling.
- CMP evidence is 1986–2007 and small-firm heavy; weights are starting values.
- form4-2 assumes the HTTP cache still holds the XML; if not, the re-parse is a full re-fetch (count shown first).
- Rows carry the first joint owner only; family entities with separate CIKs could inflate a cluster.
- Our CUSIPs may be missing from `fin_issuer_map`; name match or an owner map fills it.
- Without the plan registry, a strategically timed 10b5-1 plan reads as noise.
- Duquesne's 13F filer CIK to verify at build; "CEO of equity" unresolved until answered.
- Manager rows in `fin_holding` also appear in M02: as "other filers' 13F rows" on the Money flow tab, as K1 edges in `financing_edges`, and, when a check holds a row, as M02 review items (`check_items`). The mock-up shows whether M02 should skip followed-manager filers.
- Berkshire's submissions history is long (it files Form 4s as a 10% owner), so its first sync may take more pages than estimated; the dry run prints the count.

## Check notes (2026-10-13)
1. **Outline fit.** Item 4 (short interest) was raised here as Q07.8 although the M08 pack researched it (Round 4) and the M08 brief asks it as Q08.8: two questions on one point with different sources. Removed Q07.8; Purpose, data table and Deferred now point to Q08.8. The CRWV example (gross insider sales over 9–12 months) was not reproducible from a net that drops plan sales: gross S shares and $ added beside `insider_net_flow`.
2. **Binding decisions.** R16's 13D/G half is not met by the MVP unless Q07.6b/c; now stated in Purpose, Deferred and Q07.6b. DESIGN Q3 is an open question, so Q07.7 legitimately asks it; the outline sentence is now quoted. No question re-asks a decided point (the shares split and implied float are D-M04-2, not asked).
3. **Data reality.** All named tables, columns and functions exist (`insider_txn` incl. `plan_basis`, `form4_doc`, `cover_shares` (0029, not 0012), `price_bar`, `fin_13f`, `fin_holding`, `fin_issuer_map`, `shares.cover_counts/implied_float/close_on/splits_after`, `thirteenf.read_filing`, `signals.write_signal`, `insiders.transactions`, `DOC_TTL_S`). Corrected: (a) `thirteenf.store_rows` stores every 13F row and unresolved ones become `m02_13f_issuer` review items, so "not stored and not queued" needs a new keep-filter (case 17, Part 2); (b) a manager's filing list is not in `filing`, so Part 2 must `sync_filings` the manager first; (c) the 13F request count was 17 per manager, but `read_filing` makes 3 requests per filing (index, cover, table): now about 25–40 once, about 4 per new filing; (d) Q07.1a fetched to 2023-01-01, but `form4_years = 4` keeps a window back to ~2022-10 and the logon refresh would fetch the difference itself: now one owner run over the full 4-year window; (e) the form4-2 version bump makes the logon refresh's `sync_insiders` re-parse everything: sequencing added; (f) manager rows would also show in M02 (K1 edges, Money flow, held-row review items): added as an open risk.
4. **Numbers and sources.** Huang, Musk, Tan, Berkshire and AAPL figures recomputed and match the pack and D-SEC-10; ADV and AAPL $ remain marked illus. The AAPL line said non-plan sales warn "if not routine", contradicting Q07.3a (unclassified warns only at ≥ 10% of stake); aligned. The removed Q07.8 carried an unsourced FINRA claim and an unsourced "mega-cap short interest is small".
5. **MVP discipline / D13.** 4 signals, now 7 questions, 2 parts. Added: the `cik` key and `value`/`value_text` split (D-M04-74, D-M04-9); a rule for same-day forms, because `write_signal` upserts on (cik, module, signal, timeframe, as_of) and several Form 4s (or managers' 13Fs on the deadline day) would overwrite each other; `insider_net_flow` written per timeframe, `none` vs "missing: history starts …"; the opportunistic buy also raises the M01 rule 6 alert; `purchase_from_issuer` is kept out of net flow.
6. **Overlap.** Cover count and implied float are M04 signals (`shares_cover`, `implied_float_shares`): now named as reused, not rebuilt. M02 owns the 13F reader and 13D/G display: reused, with the side effects above. No other M02/M04 signal duplicates the 4 M07 signals.
