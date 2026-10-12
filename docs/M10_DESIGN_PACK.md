# M10 — Design review pack (draft for the owner)

**Status:** research only — nothing is decided until the owner answers (D7); 2026-10-12 · Effort: High for this review, Medium per build part. Outputs are research signals and warnings, not financial advice.

## Purpose and dependencies
**The question M10 answers:** what is the macro and policy backdrop, which names are exposed to it, and when should that raise a warning? M10 reports regimes, exposures, narratives and policy events. It does not time sectors or the market (Round 3).

**Decisions it must honour:**
- D8 and D16: it gives warnings only; the owner decides.
- D10 to D12: every output stays visible, profiles change only weights, and each warning carries the profile of record.
- D13, D14, D21, D28.
- R23 (caps on shared-killswitch exposure) and R4.
- M01 rules 4 and 6.
- S19: FRED CPI and M2 are already in M01.
- S2.
- D-UI-2: data under restricted licences stays internal.
- D-M02-12: jobs run as a logon catch-up, inside the 3-hour limit.
- D-M02-42: the market credit spread belongs to M10.
- D-M02-54/55: the macro wording that M02 mining drops belongs to M10.
- D-M02-58: the cap of 10 review items a week (S86).

**Depends on (M10 uses these and does not redesign them):**
- M00: storage, the UI, and the `signal` table (`src/engine/store/migrations/engine/0001_initial.sql:158`). Its `ticker` column is NOT NULL.
- M01: profiles.
- M04: the CvD question Q1, "Is the slump shared?". M10 gives evidence only. M04's `financing_pressure`, debt maturities (part 4) and segment facts (part 7) are proposals, not decisions.
- M02:
  - `news_item` (part 7a).
  - The official-feed adapters (part 7b). These are planned only: no code reads the Federal Register, Congress.gov, USAspending or arXiv yet (DS10).
  - Theme mining, `src/engine/themes/mining.py:67`.
  - `supply_link`, `spender_link` and `aliases.toml`.
  - Year-ago twins (D-M02-52).
- M11 uses the killswitch inputs. It has no doc yet.

**What exists today:** no macro data, no FRED code, and no `FRED_API_KEY` in `.env` (DESIGN.md key list).

**How to answer:** in plain text, e.g. "1.1a 1.2a 1.3a". Strike a suggestion by its number ("S3.4 no"), or reply "rest ok". Answers become D-M10-1 onward. Every threshold below is a starting value; Round 2 sets the real ones.

---

## Round 1 — Macro regime indicators

### What the research says
1. **Yield curve.**
   - A simple real-time model based on the long–short spread predicted recessions a few quarters ahead better than professional forecasters (S-new-M10-1).
   - The near-term forward spread is the 3-month forward rate 6 quarters ahead minus today's 3-month yield. It beats long spreads as a predictor of recessions, GDP and returns (S-new-M10-2).
   - Computing it needs the Gürkaynak–Sack–Wright yield curve. Its files update weekly and are "subject to delay, revision" (S-new-M10-22).
2. **Credit.**
   - The excess bond premium (EBP) carries most of the predictive power of credit spreads. EBP shocks lower output and equity prices (S-new-M10-3).
   - The Fed posts the EBP monthly as a CSV, and "the entire history of the EBP may revise each month" (S-new-M10-19).
   - Out of sample, a model on the term spread plus the EBP scores an AUROC of about 0.88 for "recession within 12 months". On the turning points into recession, the EBP alone scores about 0.59 (S-new-M10-20).
3. **Financial conditions.**
   - Tighter conditions on the NFCI lower the worst-case GDP outcomes a year ahead. Activity data predict only the median (S-new-M10-4).
   - The NFCI combines 105 indicators and is published weekly; a positive value means tighter than average. The ANFCI removes the part explained by activity and inflation (S-new-M10-21).
4. **Activity.**
   - FRED deleted the ISM series in 2016 (S-new-M10-17).
   - Regional Fed surveys correlate about 0.71–0.81 with the ISM (S-new-M10-24, other) and add explanatory power of their own (S-new-M10-23).
   - `IPG3344S` was 190.10 in Aug 2026. It measures US domestic chip output, so it bears directly on names with US fabs (INTC, GFS, MU) and only indirectly on the fabless NVDA and MRVL.
5. **"Net liquidity"** (Fed assets − Treasury General Account − reverse repo): no peer-reviewed evidence was found that it predicts anything (search 2026-10-12). That is an absence of evidence, not a refutation.
6. **Access** (S-new-M10-17):
   - The keyless `fredgraph.csv?id=` download works. The FRED API needs a free key.
   - Since April 2026, FRED keeps only 3 years of HY OAS, and reproducing it needs ICE's permission.
   - `BAA10Y` starts in 1986.
   - Tiingo can hold ETFs: 500 symbols a month, internal use only (S68).

### Worked example — snapshot (real values from FRED, checked 2026-10-12, S-new-M10-17)
| Indicator | Latest | Rule (illustrative) | State (illustrative) |
|---|---|---|---|
| T10Y3M | +0.99 (2026-10-09) | < 0 → watch | normal |
| HY OAS | 3.15 (2026-10-08) | above its own 3-year 80th percentile → watch | not computed |
| BAA10Y | 1.48 (2026-10-08) | set in Round 2 | not computed |
| NFCI | −0.494 (week to 2026-10-02) | > 0 → tighter than average | normal (loose) |
| SAHMREALTIME | 0.00 (Sep 2026) | ≥ 0.50 → stress | normal |
| IPG3344S | 190.10 (Aug; Jul 190.26) | 3-month change < 0 → watch | not computed |

### All cases
1. **New value:** stored with the fetch date as its vintage.
2. **Revision** (NFCI, EBP, GSW): stored as new rows; the old rows are kept.
3. **Series deleted, or an expected release missed:** shown as "stale since <date>". The last value is never carried forward silently.
4. **Source window shortened** (HY OAS): our older rows are kept.
5. **Licence-restricted series** (ICE): internal use only.
6. **Mixed frequencies:** each state shows its own as-of date.
7. **Release lag:** the as-of date is the release date.
8. **Blank value:** missing, never zero.
9. **Fetch failure:** the last state stays, labelled stale, and the run continues.
10. **Series ID not yet checked:** probed at build before use.
11. **Series that covers only some companies** (IPG3344S): linked to US-fab names only.

### Suggestions
- **S1.1** Build `src/engine/macro/fred.py` (U7) on the keyless CSV, with a fetch budget. Store values in `macro_series(series_id, date, value, vintage_date, source, licence)`.
- **S1.2** Start with about 10 series: `T10Y3M`, `T10Y2Y`, `BAA10Y`, `BAMLH0A0HYM2`, EBP, `NFCI`, `ANFCI`, `SAHMREALTIME`, `IPMAN`, `IPG3344S`, plus 2–3 regional surveys. Unchecked IDs are probed at build.
- **S1.3** Give each indicator a state (normal / watch / stress) and the date it last changed. The composite is the count of indicators in stress; there is no single score.
- **S1.4** Compute the Engstrom–Sharpe spread weekly from the GSW file.
- **S1.5** The daily logon job makes about 15 requests.
- **S1.6** Add DS12 (FRED/ALFRED) and DS13 (EBP/GSW) to DATA_SOURCES.md.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| 10y–3m inversion | Policy can cause it; the 2022–24 inversion had no recession | Shown as a probability with its hit record, never as a yes/no |
| HY OAS | Only 3 years of history; ICE licence | BAA10Y or EBP for history; internal use |
| EBP | The whole history is revised | Every vintage stored |
| Regional surveys | Noisy; regions differ | 3-month average; several regions shown |
| NFCI | Revised weekly; includes equity volatility | Labelled as financial conditions; ANFCI also shown |
| IPG3344S | Domestic output only | Linked to US-fab names only |

### Questions
**1.1 Where macro readings live**
- (a) *Recommended.* A separate `macro_reading` table; effects on individual tickers go to `signal`. Why: a shared table needs no migration, and a market reading is not a ticker signal.
- (b) A pseudo-ticker `_MACRO` in `signal`.
- (c) Make `ticker` nullable (a migration).

**1.2 Net liquidity**
- (a) *Recommended.* Leave it out; use NFCI/ANFCI. Why: it has no peer-reviewed support, and NFCI already covers liquidity.
- (b) Show it as context, labelled "unproven".
- (c) Count it in the regime composite.

**1.3 Credit history for backtests**
- (a) *Recommended.* BAA10Y + EBP for history; HY OAS for current display. Why: HY OAS now has only 3 years and an ICE licence.
- (b) HY OAS only.

---

## Round 2 — Predictive value, decay and point-in-time calibration

### What the research says
1. Of 29 newer equity-premium predictors, over a third fail even in-sample. About half of the survivors do poorly out of sample (S-new-M10-5).
2. Across 97 cross-sectional predictors, returns fall 26% out of sample and 58% after publication (S-new-M10-6). These are stock-level anomalies, so for macro signals this is an analogy, not a test.
3. The monthly average of T10Y3M was negative from Nov 2022 to Nov 2024 without a break (25 months). It was slightly negative again in Mar–Apr and Jun–Aug 2025 (S-new-M10-17). NBER's latest trough is April 2020, with no peak since (S-new-M10-25).
4. The Sahm rule fired on the July 2024 reading, yet Sahm herself said she did not believe the US was in recession (S-new-M10-26). The rule dates a recession already under way; it does not forecast one.
5. Rising unemployment lifts stocks in expansions and lowers them in contractions (S-new-M10-7). The sign of a reading depends on the regime.
6. Revisions leak into backtests:
   - ALFRED keeps every vintage, but it needs the key. Example: Q1 2014 GDP went 17,149.6 → 17,101.3 → 17,016.0 (S-new-M10-18, other).
   - The EBP and GSW files are revised in place, so our own downloads are their only vintages.
   - There have been about 8 recessions since 1970 (S-new-M10-25).

### Worked example — the 2022–24 inversion (real FRED monthly averages, S-new-M10-17)
| Month | T10Y3M | Comment |
|---|---|---|
| 2022-10 / 11 | +0.11 / −0.43 | Inversion starts |
| 2023-05 | −1.73 | Deepest |
| 2024-11 / 12 | −0.26 / 0.00 | Unbroken run ends |
| 2025-01 | +0.29 | Briefly positive |
| 2025-03, 04, 06–08 | −0.02 to −0.06 | Inverted again |
| 2025-09 on | +0.05, rising to +0.90 (2026-09) | Re-steepened |

A yes/no rule would have said "recession" for 25 months and then flickered on and off. NBER lists no peak. The indicator's record shows this as one false alarm.

### All cases
1. **Series in ALFRED:** as-of readings come from its vintages.
2. **Other series:** as-of readings come from our own downloads. History before the first download is labelled "revisions may leak".
3. **Signal followed by a recession:** a hit, with its lead time.
4. **Signal with no recession:** a false alarm.
5. **Recession with no signal:** a miss.
6. **Window still open:** pending.
7. **Readings flickering around the threshold:** one episode under the persistence rule.
8. **Few events:** the count n is shown beside every rate.
9. **Same reading, opposite meaning in different regimes:** conditioned on the regime state.
10. **Indicator published during the sample:** the record is split at the year of publication.

### Suggestions
- **S2.1** Keep every value with its `vintage_date`. Backfill ALFRED once (if 2.1a).
- **S2.2** `macro/backtest.py` answers "what did the engine say on date D?" from vintages only, the same way `discovered_at` works (D-M02-15).
- **S2.3** Each indicator page shows: signals, hits, false alarms, misses, lead time, n, sample dates and the source's publication year.
- **S2.4** A state changes only after the reading persists past the threshold.
- **S2.5** M10 weights start low in every profile. They rise only on owner approval after the backtest.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Any threshold | Fitting on the full history overstates hits | Expanding window on vintages; misses and false alarms shown |
| Few events | About 8 recessions | n beside every rate |
| Sign depends on regime | Same reading, opposite meaning | Conditioned on the regime |
| Published-signal decay | The edge fades after publication | Re-tested yearly; record since publication shown |
| Near-zero readings | The state flips monthly (2025) | Persistence rule |

### Questions
**2.1 FRED key** (no `uv add` needed; `requests` is already a dependency)
- (a) *Recommended.* The owner gets a free key for ALFRED vintages. Why: the only clean point-in-time history.
- (b) Keyless CSV only, storing our own vintages from day one.

**2.2 What M10 says before the backtest**
- (a) *Recommended.* Warnings and context only, with no confluence weight. Why: most predictors fail out of sample.
- (b) A small weight from the start.

---

## Round 3 — Sector and company sensitivity (exposure map)

### What the research says
1. **Rate surprises.**
   - An unexpected 25 bp cut has gone with about a 1% rise in the index (S-new-M10-8).
   - Tech and telecoms moved about 1.5× the market, and energy and utilities about half as much. Even so, equal responses across industries cannot be ruled out statistically (S-new-M10-8).
   - Yield changes may explain most of the reaction (S-new-M10-27, working paper).
2. **Long-duration stocks** earn about 1.10% a month less, and about three times that after periods of high sentiment (S-new-M10-9). INFQ and SPCX should be measured from M04 inputs. MSTR's value is mostly bitcoin.
3. **Sector rotation.** With perfect hindsight it beat the market by about 2.3% a year gross. Realistic timing and costs take that to zero (S-new-M10-28, other), and there is no systematic sector pattern (S-new-M10-10).
4. **Supply chains.** The 2018–19 tariff losses spread to suppliers and customers (S-new-M10-11). This is the case for using `supply_link`.
5. **Correlations** rise in sell-offs (S-new-M10-12).
6. **Data.**
   - Geographic revenue is usually reported only as dimensional XBRL, which we do not store. M04's part-7 proposal covers business and product axes only.
   - About 12 sector ETFs fit within the Tiingo cap. At about 75 s per symbol (D-M02-12), they add about 15 minutes a day.

### Worked example — the April 2025 tariff shock (real values)
| Item | Value | Source |
|---|---|---|
| HY OAS | 3.42 (Apr 2) → 4.61 (Apr 7) → 4.37 (Apr 9) | S-new-M10-17 |
| BAA10Y | 1.73 (Apr 2) → 2.02 (Apr 7 and Apr 9) | S-new-M10-17 |
| S&P 500 | −4.8% (Apr 3), about −6% (Apr 4), +9.52% (Apr 9, 90-day pause) | Secondary reports, URLs not kept; to be re-read from ETF bars at build |
| AAPL tariff cost | About $800M actual (June 2025 quarter); $1.1B estimated (Sept quarter), from the 2025-07-31 call | S-new-M10-37, other; forward-looking (S98) |

Exposure card (illustrative) for AAPL:
- Tariff cost $1.1B a quarter (from the call; grade B until matched to a filing).
- Sourcing from China, Vietnam and India (stated).
- Beta to ΔBAA10Y: not computed.

### All cases
1. **Geographic revenue stated:** grade A, with its basis (ship-to, customer HQ or end customer).
2. **Geographic revenue only in dimensional XBRL:** "missing: dimensional" (Q3.3).
3. **Exposure only in risk factors:** shown as "mentioned", not quantified.
4. **Exposure only on a call:** grade B, labelled forward-looking, until a filing matches it.
5. **SIC code misfiles a mixed firm** (AMZN, MSTR): stated exposures come first.
6. **Company that mainly holds assets:** its own duration class.
7. **Short price history** (SPCX): "insufficient history".
8. **Unstable beta:** shown with a band and an "unstable" label. Earnings weeks are excluded.
9. **Exposure through suppliers or customers:** via `supply_link`, labelled "indirect".
10. **Nothing known:** missing, never zero.

### Suggestions
- **S3.1** An exposure card of stated items, each with its source_ref and grade A:
  - revenue by country or region;
  - China end-customers;
  - export-control mentions;
  - debt maturities (M04 part 4, proposed);
  - floating-rate debt (Q3.3).
- **S3.2** Measured betas to Δ10y, ΔBAA10Y and the sector ETF, labelled "estimate".
- **S3.3** A duration class from M04 inputs: no positive FCF, or most value in distant cash flows → long-duration. Asset-holding companies get their own class.
- **S3.4** No sector-rotation signals. M10 warns about exposure; it does not rotate.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Rolling beta | Unstable; flips across regimes; earnings days dominate | 2–3-year weekly windows with a band; earnings weeks excluded; never extrapolated |
| Sector label | SIC misfiles mixed firms | Stated exposures first |
| Geographic revenue | Ship-to, HQ and end customer differ (MU's CAC case is by customer HQ) | Basis stored as stated (LESSONS) |
| Diversification | Correlations converge in stress | Shared-killswitch caps (Round 6) |

### Questions
**3.1 Source of exposure**
- (a) *Recommended.* Stated exposures first, betas second. Why: filings are grade A, and betas are unstable.
- (b) Betas only.

**3.2 Sector ETFs**
- (a) *Recommended.* Add about 12 (the 11 SPDR sector funds + SMH). Why: they fit inside the 500-symbol cap, at about 15 minutes a day, or a third of that in the 3-day rotation.
- (b) None; FRED only.

**3.3 Geographic revenue and floating-rate debt**
- (a) *Recommended.* Ask the M04 proposal to add a geographic axis to part 7 and floating-rate debt to part 4. Why: one instance reader then serves both modules.
- (b) M10 parses filing instances itself.
- (c) Leave both missing in v1.

---

## Round 4 — Narrative tracking

### What the research says
1. Popular narratives can be studied as drivers of economic swings, though reverse causality is hard to rule out (S-new-M10-13).
2. **Newspaper indices.**
   - EPU (economic policy uncertainty) counts newspaper articles and was validated against 12,000 articles read by people (S-new-M10-14).
   - The daily TPU (trade policy uncertainty) file and the categorical EPU file are licensed CC BY 4.0 (S-new-M10-29).
   - Higher TPU lowers investment at firm and aggregate level (S-new-M10-15).
   - GPR (geopolitical risk) comes daily and monthly. Its latest data are preliminary and later revised. It is licensed CC BY, and its base period needs checking (S-new-M10-16).
3. Firm-level political risk is measured as the share of a call spent on political-risk word pairs (S96). News topics track the business cycle (S83).
4. **Our pipeline already catches macro wording.**
   - The top phrases in part 6's first live check included "international emergency economic powers act".
   - Phrases with tariff, tax, act or agency words are now dropped by `mining.ADMIN` and only counted.
   - "Tariffs" (55%) and "border protection" (54%) were stopped by a different mechanism, the spread rule, as generic wording (D-M02-54/55).
   - The IEEPA wording matched a real event (S-new-M10-34, other).
5. **Data.** Stored: narrative passages, call transcripts split by speaker turn, `news_item` snippets (personal-use licences, DS4) and twins. The gap: dropped phrases are only counted, not kept.

### Worked example (illustrative, apart from Apple's figures)
| Company | Topic | Document | Management share | Year-ago twin | Flag |
|---|---|---|---|---|---|
| AAPL | tariffs/trade | FY25 Q3 call | to compute | FY24 Q3: to compute | rise; $800M actual, $1.1B estimate (S-new-M10-37) |
| MU | export controls | FY26 Q4 call | 0.8% (illustrative) | 0.3% (illustrative) | rise |

### All cases
1. **Topic appears for a company for the first time:** first-mention flag.
2. **Topic share rises against the company's own twin:** rise flag.
3. **Topic share falls:** shown, no flag.
4. **No twin** (SPCX): no flag.
5. **Corpus composition changes:** compared with the twin only, never as raw levels.
6. **The same law's wording appears everywhere:** an aggregate narrative, not a company flag.
7. **Boilerplate risk factors:** narrative sections only, and only changes count.
8. **Analyst raises a topic, management dismisses it:** management and analyst shares kept separate.
9. **Accounting-rule phrases** (ASU 2023-09, "pillar two"): not macro.
10. **Phrase in both a theme and a macro topic:** counted in both.
11. **Outside index revised:** the vintage is stored.
12. **Transcript missing:** missing.

### Suggestions
- **S4.1** M02 mining writes the admin phrases it drops, and the spread-rule failures, to an `m10_phrase` table (phrase, company, document, section, season). This costs no extra SEC requests.
- **S4.2** `config/macro_topics.toml` holds about 8 topics: tariffs/trade, export controls, rates, inflation, recession/demand, FX, fiscal/tax and geopolitics. The owner approves additions.
- **S4.3** For each company and quarter: the topic's share of management turns and narrative sections, against the twin.
- **S4.4** An aggregate: the share of watchlist and tracked names mentioning each topic per season, with daily EPU/TPU as the outside reference.
- **S4.5** One weekly review item (Q4.3).

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Phrase share | Corpus changes (LESSONS: 220 vs 32 documents) | Compare with the company's own twin (D-M02-52) |
| Boilerplate | Risk factors repeat every risk | Narrative sections; changes only (D-M02-54) |
| Shared law wording | Not a company signal | Spread rule applied in reverse → aggregate |
| Newspaper indices | Attention is not impact; reverse causality | Context only until backtested |
| Analyst questions | Management may dismiss them | Separate shares (D-M02-6) |
| Gemini labels | Precision not measured | Hint only, after blind labelling (D-M02-40) |

### Questions
**4.1 Lexicon**
- (a) *Recommended.* Owner-approved phrase sets, with the phrases M02 drops proposed as additions. Why: the same reviewable pattern as themes.
- (b) Adopt the Hassan et al. word-pair method wholesale (S96).
- (c) Gemini classifies passages (needs measuring first).

**4.2 Outside indices**
- (a) *Recommended.* Daily EPU + TPU only. Why: free, CC BY 4.0, peer-reviewed, and they cover trade.
- (b) Add GPR (base period to confirm).
- (c) None.

**4.3 Review volume**
- (a) *Recommended.* One weekly `m10_macro` item, counted in the 10-a-week cap. Why: keeps macro apart from theme news.
- (b) Merge into `m02_news`.

---

## Round 5 — Policy events (tariffs, export controls, regulators)

### What the research says
1. **The Federal Register API needs no key and filters well** (S94). Checked 2026-10-12 (S-new-M10-30):
   - In 2026 there are 4 presidential documents on "semiconductors".
   - One is Proclamation 11002 (Section 232). It sets a 25% duty on advanced logic chips defined by processing-performance and DRAM-bandwidth thresholds, with exemptions such as US data centers (S-new-M10-32, other).
   - It names no product, so any product mapping is press inference.
   - Also found: Proclamation 11052 on polysilicon (FR 2026-16400), and 12 BIS final rules among 43 BIS documents (Entity List, UAE, licence policy for advanced computing).
2. **Publication lags, and some reversals are never published.**
   - The AI Diffusion rule (FR 2025-00636) was rescinded by press release on 2025-05-13, with a Federal Register notice still pending (S-new-M10-33, other).
   - The FAA's emergency AD for the 737-9 reached operators on 2024-01-06; the Register published it on 2024-01-18 (S-new-M10-30).
3. **Company 8-Ks often come first.** NVIDIA was notified on 2025-04-09 of the H20 licence requirement and expected "up to approximately $5.5 billion" of charges. The actual charge was $4.5B (S-new-M10-31).
4. **Foreign actions and court rulings never reach the Register.**
   - China's CAC barred critical-infrastructure buyers from Micron products on 2023-05-21. Mainland revenue was about 11% ($3.3B of $30.7B) (S-new-M10-35, other).
   - The IEEPA tariffs were struck down on 2026-02-20, and a 10% Section 122 tariff was reported alongside the ruling (S-new-M10-34, other).
5. **Congress.gov** has no keyword search. Bills filter by congress and type, with a policyArea field on each bill (S-new-M10-36). The limit is 5,000 requests an hour (DS10).
6. **Data.**
   - Already built: 8-K events, IR RSS, Finnhub/Massive (97% of Finnhub items are grade C, D-M02-59).
   - Agency filters that worked: `industry-and-security-bureau`, `federal-aviation-administration`, `PRESDOCU`. USTR, ITA, FCC and DoD are not checked yet.

### Worked example — one policy event row (real data; company links illustrative)
| Field | Value |
|---|---|
| Document | Proclamation 11002, FR 2026-01052; Executive Office of the President |
| Signed / effective / published | 2026-01-14 / 2026-01-15 / 2026-01-20 |
| Topic | tariffs/trade; semiconductors (Section 232) |
| Named products | None — thresholds only |
| Linked (illustrative) | NVDA, AMD-type accelerator vendors; MU, INTC, GFS, MRVL — all "possible exposure" |
| Status / grade | In force as issued (later changes not checked) / A |

### All cases
1. **Rule published:** grade A, with all three dates. The event date follows Q5.3.
2. **`effective_on` empty:** read from the text, or left missing.
3. **Rule reversed by press release or court:** news or an 8-K proposes the new status; the owner confirms.
4. **Foreign regulator:** covered only by news (grade B/C) and 8-Ks (grade A).
5. **Company 8-K before any rule:** stored as a company event and linked to the rule later.
6. **Product named in the text** (H20, 737-9): an alias link is proposed.
7. **Coverage by thresholds only:** "possible exposure".
8. **False keyword match** (drones, firearms in BIS lists): agency and type filters, then owner review.
9. **Bill only introduced:** hidden.
10. **Correction:** linked to the original document.
11. **Same action in several feeds:** one event with several sources.

### Suggestions
- **S5.1** An agency watch list in `config/policy.toml` (BIS, USTR, ITA, Section 232, FAA, FCC, presidential documents), run on the 7b adapter. A daily delta pull costs about 5 requests.
- **S5.2** A `policy_event` table: document number, agency, type, the three dates, status, topics, matched companies, grade and source_ref.
- **S5.3** Link by product name or alias, otherwise by exposure class. The owner confirms links in the weekly item.
- **S5.4** Words like "rescind", "not enforce", "vacated" or "struck down" near a tracked policy in 8-Ks or news raise a review item.
- **S5.5** Pull Congress weekly, in the Q5.2 policy areas, showing only bills past committee.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Register date | Lags signing and effect | Three dates stored; the earliest is the event date |
| Reversed rules | The Register still shows them in force | Status from news or 8-Ks; owner confirms |
| Keyword match | Catches unrelated rules | Agency and type filters, aliases, review |
| Bills | Most never pass | Only bills past committee |
| Company impact | Rule texts rarely name companies | "Possible exposure" until the company states its impact |

### Questions
**5.1 Who builds the fetch**
- (a) *Recommended.* Extend M02 7b's adapter; M10 owns matching and status. Why: one adapter and one request budget (U7).
- (b) A separate M10 adapter.

**5.2 Congress scope**
- (a) *Recommended.* Only bills with committee or floor action in "Foreign Trade and International Finance", "Taxation" and "Science, Technology, Communications". Why: few items, and the policy area can be filtered on each bill.
- (b) All introduced bills that name watchlist companies.
- (c) Skip Congress in v1.

**5.3 Event date**
- (a) *Recommended.* The earliest of signed, announced and effective, with the publication date kept. Why: publication lagged 6–12 days in the examples.
- (b) Publication date only.

---

## Round 6 — Feeding M11 killswitches, M01 and M04

### What the research says
1. R23 is approved, and M01 rule 4 makes killswitch hits exit warnings (D16).
2. Correlations converge in shocks (S-new-M10-12). One event like the H20 rule would hit every China-exposed chip name at once.
3. Financial conditions predict the bad-outcome tail, not the median (S-new-M10-4). So macro fits best as a risk-of-loss warning (D8).
4. Broad stress makes M04's "shared slump" more likely, but M04 does the classifying.
5. The `position`, `lot` and `decision` tables exist (migration 0001). M11 has nothing yet.

### Worked example — shared killswitch view (illustrative; the events are real)
| Killswitch | Trigger | Holdings | Weight | Cap | State |
|---|---|---|---|---|---|
| China export controls | A new BIS rule or proclamation matching a stated exposure | NVDA (FR 2026-01052, owner-confirmed in this illustration), MU, MRVL | 34% | 25% | Over the cap → warning |
| Credit stress | BAA10Y in stress for 4 weeks | MSTR, INFQ | 9% | 15% | Not tripped |
| Rate shock | 10-year yield up 100 bp in 6 months | SPCX, INFQ | 7% | 10% | Not tripped |

A real reference point: BAA10Y peaked at 2.02 on 2025-04-07 and 2025-04-09 (S-new-M10-17). Whether that counts as "stress" depends on the calibration.

### All cases
1. **Stated or owner-confirmed exposure plus a matching event:** exit warning and event alert.
2. **Possible exposure only:** a banner, never a trip.
3. **Stress with no company link:** follows Q6.1.
4. **Stress shorter than the persistence rule:** "watch".
5. **Stress on one indicator only:** follows Q6.2.
6. **Several holdings on one killswitch:** their combined weight is compared with the cap.
7. **One holding on several killswitches:** counted in each.
8. **Killswitch defined after the event:** never applied backwards. Edits are logged.
9. **Core lot and overlay on different profiles (D11):** each judged on its own profile.
10. **Stress clears:** the change is dated and the history kept.
11. **No positions entered:** tickers listed without weights.
12. **M11 not built yet:** M10 publishes readings only.
13. **Company slump during broad stress:** an evidence row for M04's Q1.

### Suggestions
- **S6.1** Readings go to the Q1.1 store; per-ticker records go to `signal` (see Signals out).
- **S6.2** Killswitch templates for M11:
  - **Policy:** a new rule matched to a stated exposure.
  - **Credit:** BAA10Y or EBP in stress for 4 weeks or more, for names that depend on financing (via M04's `financing_pressure`).
  - **Rates:** the 10-year yield up 100 bp in 6 months (illustrative), for long-duration names.
  - **Demand:** IPG3344S or regional new orders down for 3 months, for chip names.
- **S6.3** A shared-exposure view: the weight on each killswitch against the owner's cap (R23).
- **S6.4** By profile:
  - MY: context, with persistence.
  - PT: weight only after the backtest.
  - ST: event alerts.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Macro killswitch | Fires on noise; alert fatigue | Persistence, two indicators, hit record shown |
| Killswitch set after the fact | Hindsight | Set at thesis entry and dated (R4); changes logged |
| Guessed exposure | Needless warnings | Only stated or confirmed links trip |
| Timeframe mismatch | ST stress on an MY holding | Profile of record (D12) |

### Questions
**6.1 Can macro trip a killswitch on its own?**
- (a) *Recommended.* Only with a stated or owner-confirmed exposure; otherwise a banner. Why: avoids market-wide alert fatigue (S86).
- (b) Market-wide stress warns on every holding.

**6.2 Persistence for MY**
- (a) *Recommended.* 4 weeks and 2 indicators. Why: it filters out the 2025 flicker.
- (b) One indicator, immediately.
- (c) The owner sets it per killswitch.

**6.3 Who owns killswitch definitions**
- (a) *Recommended.* M11 owns them; M10 publishes readings and events. Why: R23 and R4 belong to M11.
- (b) M10 owns the macro killswitches.

---

## Signals out (proposal, stored as in 1.1a)
| Signal | Store | Value | MY | PT | ST |
|---|---|---|---|---|---|
| `macro_regime` | `macro_reading` | normal/watch/stress per indicator; count in stress | Context banner | Modest weight after backtest (2.2) | Context |
| `policy_event_exposure` | `signal` | 1 = stated or confirmed link | Killswitch input (6.1) | Warning | Event alert (M01 rule 6) |
| `macro_exposure_warning` | `signal` | 1 = linked indicator in stress past persistence | Warning (6.2) | Warning | Context |
| `narrative_topic_rise` | `signal` | change in share vs twin (percentage points) | Context | Context | Context |
| `macro_sensitivity` | `signal`, method "estimate" | beta with band | Context | Context | Context |
| `duration_class` | exposure card | long / short / asset-holding | Decides which names the rate killswitch covers | Context | — |

Example (illustrative): `{ticker: "NVDA", module_id: "M10", signal: "policy_event_exposure", value: 1, timeframe: "MY", evidence_grade: "A", source_ref: "FR 2026-01052", method: "technical-threshold match + owner confirm", as_of: "2026-01-20"}`.

## Build parts (proposal)
Each part is one conversation at Medium effort, on branches `m10-part1` onward. Each part updates the module doc in the same commit and adds fixture tests. Each part has one combined owner live run, a few minutes long, with the log sent back.

| Part | Contents | Depends on | Live check |
|---|---|---|---|
| 1 Macro series | FRED adapter (plus ALFRED if 2.1a), `macro_series`, EBP/GSW files, states with persistence, Q1.1 store, Macro page, DS12/DS13 | — | About 15 series + EBP + GSW; snapshot, request count, run time |
| 2 Calibration | `macro/backtest.py`, `USREC`, indicator records; owner approves thresholds | 1 | ALFRED backfill; backtest report |
| 3 Exposure card | Stated exposures, betas, duration class, sector ETFs | 1; M04 parts 1, 4 and 7 for full cards | ETF backfill; instance reads if 3.3b |
| 4 Narrative | `m10_phrase` from M02 mining, `macro_topics.toml`, shares vs twins, aggregate, EPU/TPU, weekly item | 1; M02 part 6 | One seasonal pass with phrase capture; EPU/TPU fetch |
| 5 Policy events | `policy.toml`, `policy_event`, dates, status, matching, Congress | M02 7b; parts 3 and 4 | 2026 Federal Register delta for the watch list; one Congress pull |
| 6 Signals and killswitch feed | D13 writer, warnings, killswitch templates, shared view, M04 Q1 evidence, profile weights | Parts 1–5; M11 doc | One full logon run: time, requests, signals |

## Known gaps
- Data limits:
  - PMIs are paid.
  - HY OAS has a short window and an ICE licence.
  - Net liquidity has no support.
  - There have been only about 8 recessions.
- Exposure limits:
  - Geographic revenue is dimensional.
  - China end-customers are often not stated.
  - Floating-rate debt is outside M04's proposal.
- Courts, CBP, CAC and MOFCOM are covered only through news and 8-Ks.
- Design gaps:
  - `signal.ticker` is NOT NULL.
  - M11 has no doc.
  - The S&P 500 TR proxy is still open in M01.
- Not verified:
  - FRED IDs `USEPUINDXD`, `IPMAN`, `NEWORDER`, `USREC` and the regional surveys.
  - FRED API rate limits.
  - The contents of the EBP CSV.
  - GPR's base period (the authors' slides say 1985–2019).
  - The Federal Register public-inspection endpoint.
  - The USTR, ITA, FCC and DoD agency filters.
  - Proclamation 11002's later status, and any mapping of its thresholds to products.
  - Micron's "about half of China-HQ customer revenue at risk". This needs Micron's FQ3 2023 release or FY2023 10-K.
  - AAPL and BA price moves around these events.
  - The April 2025 S&P 500 daily moves.

## New sources
These IDs are provisional. They get S-numbers after M04's S-new block when added to SOURCES.md. Reused: S19, S68, S83, S86, S94, S96, S98. "Other" means not peer-reviewed, or secondary.
- **S-new-M10-1** Rudebusch & Williams (2009), JBES 27(4) — https://ideas.repec.org/a/bes/jnlbes/v27i4y2009p492-503.html
- **S-new-M10-2** Engstrom & Sharpe (2019), FAJ 75(4) — https://rpc.cfainstitute.org/research/financial-analysts-journal/2019/0015198x-2019-1625617
- **S-new-M10-3** Gilchrist & Zakrajšek (2012), AER 102(4) — https://www.nber.org/papers/w17021
- **S-new-M10-4** Adrian, Boyarchenko & Giannone (2019), AER 109(4) — https://www.aeaweb.org/doi/10.1257/aer.20161923
- **S-new-M10-5** Goyal, Welch & Zafirov (2024), RFS 37(11) — https://ideas.repec.org/a/oup/rfinst/v37y2024i11p3490-3557..html
- **S-new-M10-6** McLean & Pontiff (2016), JF 71(1) — https://doi.org/10.1111/jofi.12365
- **S-new-M10-7** Boyd, Hu & Jagannathan (2005), JF 60(2) — https://www.nber.org/papers/w8092
- **S-new-M10-8** Bernanke & Kuttner (2005), JF 60(3) — https://www.federalreserve.gov/econres/feds/what-explains-the-stock-market39s-reaction-to-federal-reserve-policy.htm ; NBER w10402
- **S-new-M10-9** Weber (2018), JFE 128(3) — https://www.nber.org/papers/w22520
- **S-new-M10-10** Molchanov & Stangl (2023), Int. J. Finance & Economics — https://mro.massey.ac.nz/handle/10179/69590
- **S-new-M10-11** Huang, Lin, Liu & Tang (2023), JIE 145, 103811 — https://scholars.hkbu.edu.hk/en/publications/trade-networks-and-firm-value-evidence-from-the-us-china-trade-wa/
- **S-new-M10-12** Ang & Chen (2002), JFE 63(3) — https://ideas.repec.org/a/eee/jfinec/v63y2002i3p443-494.html
- **S-new-M10-13** Shiller (2017), AER 107(4) — https://www.nber.org/papers/w23075.pdf
- **S-new-M10-14** Baker, Bloom & Davis (2016), QJE 131(4) — https://nber.org/papers/w21633
- **S-new-M10-15** Caldara, Iacoviello, Molligo, Prestipino & Raffo (2020), JME 109 — https://ideas.repec.org/a/eee/moneco/v109y2020icp38-59.html
- **S-new-M10-16** Caldara & Iacoviello (2022), AER 112(4); GPR data CC BY — https://matteoiacoviello.com/gpr.htm
- **S-new-M10-17** FRED, checked 2026-10-12: API key https://fred.stlouisfed.org/docs/api/api_key.html ; ISM removal https://fred.stlouisfed.org/series/NAPM ; https://fred.stlouisfed.org/series/IPG3344S ; keyless CSV https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID> for T10Y3M, BAMLH0A0HYM2, BAA10Y, NFCI, SAHMREALTIME, IPG3344S
- **S-new-M10-18** fredapi README, ALFRED vintages (other) — https://github.com/mortada/fredapi
- **S-new-M10-19** FEDS Notes (2016-10-06), recession risk and the EBP — https://www.federalreserve.gov/econres/notes/feds-notes/updating-the-recession-risk-and-the-excess-bond-premium-20161006.htm ; CSV https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv
- **S-new-M10-20** Pike & Vazquez-Grande (2019-12-13), FEDS Notes — https://www.federalreserve.gov/econres/notes/feds-notes/out-of-sample-performance-of-recession-probability-models-20191213.htm
- **S-new-M10-21** Chicago Fed, About the NFCI — https://www.chicagofed.org/research/data/nfci/about
- **S-new-M10-22** Gürkaynak, Sack & Wright, Treasury yield curve, FEDS 2006-28 — https://www.federalreserve.gov/pubs/feds/2006/200628/200628abs.html
- **S-new-M10-23** Dallas Fed, Economic Letter 9(12), 2014 — https://fraser.stlouisfed.org/files/docs/publications/frbdal_el/frbdal_el_201412.pdf
- **S-new-M10-24** Econoday (2023-01-19), NY and Philadelphia manufacturing surveys (other) — https://www.econoday.com/articles/what-do-the-new-york-and-philadelphia-manufacturing-surveys-tell-us
- **S-new-M10-25** NBER business cycle dating — https://www.nber.org/research/business-cycle-dating
- **S-new-M10-26** CRS Insight IN12410 (2024-08-26) — https://www.everycrsreport.com/reports/IN12410.html
- **S-new-M10-27** Nagel & Xu (2024), NBER w32884 (working paper) — https://nber.org/papers/w32884
- **S-new-M10-28** Stangl, Jacobsen & Visaltanachoti (2009 draft), via CXO Advisory (other) — https://www.cxoadvisory.com/economic-indicators/perfect-sector-rotation
- **S-new-M10-29** Baker, Bloom & Davis, TPU and categorical EPU data, CC BY 4.0 — https://www.policyuncertainty.com/trade_uncertainty.html
- **S-new-M10-30** Federal Register documents via the S94 API (https://www.federalregister.gov/developers/documentation/api/v1), checked 2026-10-12: FR 2026-01052, 2026-16400, 2025-00636, 2024-00993
- **S-new-M10-31** NVIDIA 8-K (2025-04-09) — https://www.sec.gov/Archives/edgar/data/1045810/000104581025000082/nvda-20250409.htm ; Q1 FY26 release — https://www.sec.gov/Archives/edgar/data/1045810/000104581025000115/q1fy26pr.htm
- **S-new-M10-32** EY Tax News 2026-0209 (other) — https://taxnews.ey.com/news/2026-0209
- **S-new-M10-33** Akin Gump, AI Diffusion rescission alert (other) — https://www.akingump.com/en/insights/alerts/bis-rescinds-its-ai-diffusion-rule-and-issues-compliance-guidance-regarding-advanced-computing-items
- **S-new-M10-34** K&L Gates, IEEPA decision summary, 2026-02-20 (other) — https://www.klgates.com/Summary-Supreme-Court-Decision-on-IEEPA-Tariffs-2-20-2026
- **S-new-M10-35** Yicai Global (2023-05-22), Micron CAC review (other) — https://yicaiglobal.com/news/20230522-03-us-chipmaker-micron-fails-chinas-cybersecurity-review
- **S-new-M10-36** Congress.gov API, Bill endpoint docs — https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/BillEndpoint.md
- **S-new-M10-37** TechCrunch (2025-07-31), Apple tariff costs (other) — https://techcrunch.com/2025/07/31/apple-projects-tariff-costs-will-hit-1.1b-next-quarter/
