# M06 — Design review pack (draft for the owner)

**Status:** research only — nothing is decided until the owner answers (D7); 2026-10-12 · Effort: High for this review, Medium per build part. Outputs are research signals, not financial advice.

**How to answer.** Per round in plain text, e.g. "1.1a 1.2a 1.3b". Suggestions stand or fall with the answers; strike any by number ("S2.4 no") or reply "rest ok". Answers become D-M06-1 onward. Thresholds are starting values, calibrated on owner-labelled cases. Citations: S-numbers from SOURCES.md; provisional S-new-M06-n (see "New sources"); "M04 pack S-new-n" = provisional IDs in M04_DESIGN_PACK.md.

## Purpose and dependencies
**Purpose.** Per equity: is there a moat, from which source, how long should it last, which way is it moving, and who is attacking it? Feeds the MY entry gate (R1, A3) and M04's franchise question (CvD Q2).

**Approved revisions to honour:** R1 (invest only with a moat → MY gate) · R8 (HBM three-supplier oligopoly at volume → efficient-scale case) · A3 (moat duration ≥ timeframe) · R21 (named challengers: sampling → small-scale → volume → qualified at a major customer; buyer trust read at qualification) · R10 (AMD–Google ASIC grade C; AVGO–Google confirmed) · D8, D9, D10, D12, D13, D14, D16, D19, D21/D28, S2.

**Depends on**
- **M01:** weights (moat leads in MY); MY horizon open ("thesis-driven, no fixed maximum"); rule 4 exit warnings; rule 6 event alerts.
- **M02:** `supply_link` L1–L3 and `input_category` (migration 0020); `news_item`/`news_company`/`news_theme` and first mentions (0025); themes (`hbm_packaging`); `config/aliases.toml`.
- **M04:** peers (D19); CvD Q2 row "Moat (M06), challengers (R21)"; stickiness classes (D-M04-1); pack part 1 concept additions and `facts_as_of` (pack S1.1); segments (part 7); customer concentration (DS12); survival gate; cycle dates.
- **M11** consumes the gate; shared open item "milestone dismissals → R4 tracker (M06/M11)". **M03** type A drives UNRATED; **M08/M09** time entries. Q2, Q3, Q5 do not touch M06.

---

## Round 1 — Quantitative evidence: ROIC persistence and margin stability

### What the research says
1. Moat = structural excess profit, ROIC > WACC. Narrow: excess returns more likely than not for ≥ 10 years; wide: very high confidence for 10, more likely than not for 20. Set by committee (S14 = S-new-M06-1, pp. 1–2).
2. Profitability mean-reverts ≈ 38%/year, faster below the mean or far from it (M04 pack S-new-55, abstract). Our arithmetic (0.62^k): half-life ≈ 1.45 years; 9% left after 5 years, 0.8% after 10. A 10-year moat claim says the firm is an exception; a high level alone is not evidence of persistence.
3. Industry effects persist longer than firm effects (S-new-M06-4).
4. Conditioning on earnings volatility improves earnings prediction and exposes analyst errors → stability, not just level (S-new-M06-10, abstract only).
5. Gross profit ÷ assets predicts returns about as well as book-to-market; the "cleanest" profitability measure (S-new-M06-9).
6. Long-term earnings growth shows no persistence beyond chance → growth is not a moat measure (S-new-M06-5).
7. Return level and investment level both relate positively to fade (p. 6); consumer advantages show as high GM, production advantages as high asset turnover, often lower GM (pp. 37, 40); CFROI = margin × turnover (p. 40) (S-new-M06-2).
8. Intangible capital is a large off-balance-sheet share of capital (S-new-M06-11). Our inference, not the paper's: book ROIC of R&D-heavy firms is likely overstated; recipe unverified.
9. **Data.** `series` (`sec/xbrl_facts.py`) holds revenue, COGS, GP, OI, NI, R&D, SG&A, D&A, capex, CFO, interest, PP&E, cash, ST investments, assets, equity, LT debt (fallback `LongTermDebtAndCapitalLeaseObligations`), RPO; first and latest values; history from ≈ 2009 (M04 pack S-new-4). Unmapped: tax expense, pretax income, current debt, leases, goodwill, NCI, deferred revenue (with M04 part 1). Segment margins are dimensional (S41). WACC is not free data.

### Worked example
Gross margin %, latest-filed 10-K values (S-new-M06-17, checked 2026-10-12):

| FY | INTC | MSFT | NVDA | MU |
|---|---|---|---|---|
| 2016 | 61.0 | 64.0 | 56.1 | — |
| 2018 | 61.7 | 65.2 | 59.9 | 58.9 |
| 2020 | 56.0 | 67.8 | 62.0 | 30.6 |
| 2022 | 42.6 | 68.4 | 64.9 | 45.2 |
| 2023 | 40.0 | 68.9 | 56.9 | −9.1 |
| 2024 | 32.7 | 69.8 | 72.7 | 22.4 |
| 2025 | 34.8 | 68.8 | 75.0 | 39.8 |
| 2026 | — | 67.9 | 71.1 | 80.7 |

- Spread (own fiscal years; MSFT June, NVDA late Jan, MU ≈ Sep, INTC Dec): MSFT 5.7 pp (sd 2.0); INTC 29.0 pp (29.6 with FY2017's 62.3%); NVDA 18.9; MU 89.8.
- MU FY2026: revenue $133.188B, GP $107.504B (10-K 2026-10-09, acc. 0000723125-26-000023). INTC operating income: 2021 $19.456B, 2022 $2.334B, 2023 $0.093B, 2024 −$11.678B, 2025 −$2.214B.
- MSFT FY2026 ROIC (book, simplified; inputs real, method illustrative; $B): tax 32.185 ÷ 165.934 = 19.4%; NOPAT 155.237 × 0.806 ≈ 125.1; invested capital (equity + LT debt − cash & ST inv.) FY25 343.479 + 40.152 − 94.565 = 289.066, FY26 442.387 + 31.067 − 76.843 = 396.611; ROIC on the average ≈ **36.5%**. Leases and current debt are excluded (unmapped), which overstates it.

### All cases
1. ≥ 10 annual points → full statistics; 7–9 → shown, "short window"; < 7 (SPCX, INFQ) → `UNRATED (history)`.
2. Different fiscal year ends → own years; peers use M04's offset tolerance.
3. Tag switch or one-tag gap (NVDA FY2019 `Revenues`) → `facts_as_of` walk; still missing → ratio missing, never interpolated.
4. Negative or tiny invested capital → `not_meaningful` (D-SRCH-15 pattern).
5. Large cash or non-operating stakes (MSFT equity investments) → cash subtracted, stakes flagged.
6. Acquisition year → ROIC with and without goodwill.
7. R&D-heavy (NVDA, INTC, MRVL) → R&D-capitalised column.
8. Pretax near zero → tax outside 0–40% → statutory 21%, tagged.
9. Cyclical (MU) → full-cycle median and trough. Operating losses (INTC) → negative ROIC kept.
10. Leases/current debt unmapped → "excludes leases and current debt" label.
11. Restatements → backtests first-reported, display latest.
12. Moat in one segment → "consolidated only" until segment rows.
13. Fund (ETV) or asset vehicle (MSTR) → `N/A`.

### Suggestions
- **S1.1** `m06_metrics` per company-year: GM, OM, asset turnover, ROIC (book), ROIC (R&D-capitalised), spread to hurdle, method tag.
- **S1.2** Persistence: share of last N years with ROIC > hurdle; trough ROIC and GM; GM dispersion on M04's approved robust scale (IQR ÷ 1.35), or scaled MAD if M04 adopts it; peer GM-gap robust z (M04).
- **S1.3** Margin × turnover label ("consumer-type" / "production-type") as a Round 2 hint, never a verdict.
- **S1.4** Point-in-time inputs via `facts_as_of` so backtests use only what was known then.

### Failure modes (rows for M06_MOAT.md)
| Indicator | How it misleads | Guard |
|---|---|---|
| Book ROIC | Buybacks inflate it, goodwill deflates it, cash and stakes distort capital | With/without goodwill; cash subtracted; `not_meaningful` for tiny capital |
| ROIC, R&D-heavy | Expensed R&D understates capital (inference) | R&D-capitalised column, labelled |
| Tax rate | Near-zero pretax base | Outside 0–40% → 21%, tagged |
| Peak margins | MU FY2026 GM 80.7% looks like a moat | Full-cycle median and trough |
| Short history | < 7 points cannot show persistence | `UNRATED (history)` |
| Tag gaps | NVDA FY2019 missing from one tag | Missing, never interpolated |
| Unmapped liabilities | ROIC overstated (MSFT) | Label until mapped |

### Questions
**1.1 ROIC hurdle**
- (a) *Recommended.* Fixed owner-set after-tax hurdle (e.g. 8%), ±2 pp sensitivity shown. Why: transparent, stable; WACC is not free.
- (b) CAPM WACC from FRED 10-year plus an assumed premium.
- (c) Peer median ROIC.

**1.2 ROIC definition**
- (a) *Recommended.* Book ROIC primary plus an R&D-capitalised column for NVDA, INTC, MRVL. Why: simple measure with its known bias beside it.
- (b) Book only.
- (c) Capitalised R&D only.

**1.3 Persistence window**
- (a) *Recommended.* Longer of 10 fiscal years or one full cycle (M04 dates). Why: matches the narrow claim; stops peaks deciding.
- (b) Fixed 10 years.
- (c) Fixed 5 years.

---

## Round 2 — Moat sources and measurable evidence (including R8)

### What the research says
1. Five sources: intangible assets, switching costs, network effect, cost advantage, efficient scale; no-moat when a value-destroying threat is likely enough (S-new-M06-1, p. 2).
2. Switching-cost types: contractual commitments, durable purchases, brand-specific training, information and databases, specialised suppliers, search costs, loyalty programmes (S-new-M06-2, pp. 38–39).
3. Network effects are strong in interactive networks, modest in hub-and-spoke ones, and can still fizzle (AOL, MySpace, Friendster) (S-new-M06-2, pp. 39–40; basis S-new-M06-12, record only).
4. A 10-K competition-discussion measure relates to faster diminishing returns on investment, distinct from concentration (S-new-M06-6; abstract; word list unverified).
5. Text-based fluidity measures competitive threat (S-new-M06-7); data 1989–2023, no login, licence unstated, keyed by gvkey not CIK.
6. R8 holds at Q2 2026: HBM revenue shares SK hynix 50%, Samsung 33%, Micron 18% (S-new-M06-15, extends S06).
7. **Data.** Intangibles: GM, peer gap, R&D intensity (stored); patents unchecked. Switching: `rpo` (stored), deferred revenue (unmapped), stickiness class, retention wording (FTS5, DS1). Network: user KPIs in stored EX-99.1, unparsed (same gap as DS2). Cost: turnover and GM vs peers. Efficient scale: shares from B-grade pages (no API), `supply_link`. Competition trend needs DS7. Morningstar ratings are proprietary, not an input.

### Worked example
| HBM share (B) | Q2 2025 | Q1 2026 | Q2 2026 |
|---|---|---|---|
| SK hynix | — | 58% | 50% |
| Samsung | 15% | 21% | 33% |
| Micron | — | 21% | 18% |

Counterpoint via Edaily / SamMobile. Industry: three suppliers at volume → efficient scale intact. Firm (MU): share fell one quarter → "watch", not "negative" (illustrative rule). MSFT (illustrative): switching costs (commercial RPO, enterprise contracts) and network (developer/ISV ecosystem), evidenced by RPO and quoted 10-K passages; RPO not fetched for this pack.

### All cases
1. One source with metric and quoted evidence → candidate; several (MSFT) → one row each.
2. Source in one segment (AWS within AMZN) → segment rows or "consolidated only".
3. Industry intact, firm losing share (MU) → two ratings.
4. Evidence only from B-grade pages → grade B.
5. KPI definition change (Meta's DAP replaced DAU/MAU) → break flag.
6. KPI only on calls (AAPL installed base) → DS1.
7. RPO undisclosed or limited by expedients (S79) → missing, not zero.
8. Cost classification differs (Amazon fulfilment, M04 pack S-new-22) → curated peers only (D19).
9. Non-SEC rivals (SK hynix, Samsung) → shares by name, financials missing.
10. Gemini hint without a verified quote → rejected (D21); owner rejection kept with reason.
11. Metric pattern without a named source → hint only.

### Suggestions
- **S2.1** `m06_source`: company × source, evidence items (metrics, passages, supply links, news), grade, status candidate/confirmed/rejected.
- **S2.2** Pattern proposals: high stable GM → intangibles or switching; high turnover with cost-peer gap → cost advantage; few suppliers at volume → efficient scale.
- **S2.3** Gemini quotes only as owner-requested hints (D21, D28); owner confirms (D8).
- **S2.4** Share entry form: market, vendor, share, period, URL, grade B; per period.
- **S2.5** Li–Lundholm–Minnis-style competition column once DS7 lands.
- **S2.6** Extend the DS2 KPI extractor to META users and AAPL installed base (DS1).

### Failure modes (rows for M06_MOAT.md)
| Indicator | How it misleads | Guard |
|---|---|---|
| Oligopoly (R8) | Intact while one member loses share | Industry and firm rated separately |
| Competition words | Boilerplate; same-year wording across filers (LESSONS) | Narrative sections; own prior 10-K |
| User KPIs | Definitions change | Store definition sentence; flag breaks |
| RPO | Expedients omit short contracts (S79) | Only where disclosed |
| GM as consumer advantage | Cost classification differs | Curated peer group (D19) |
| Consolidated data | Segment moat hidden | Segment rows or label |

### Questions
**2.1 Source taxonomy**
- (a) *Recommended.* Morningstar's five. Why: widely understood; each maps to evidence.
- (b) Mauboussin's production / consumer / external.
- (c) Both.

**2.2 Market shares**
- (a) *Recommended.* Owner-entered with URL, grade B, prompted quarterly for HBM, x86 server, foundry. Why: only free route with a source per figure.
- (b) Gemini quotes from stored news snippets, verified.
- (c) Skip.

**2.3 Firm vs industry**
- (a) *Recommended.* Two ratings; the gate uses the firm rating. Why: R8 can hold while MU loses ground.
- (b) Firm only.

---

## Round 3 — Moat duration and trend (A3)

### What the research says
1. Bands: narrow ≥ 10 years, wide ≥ 20; DCF fade from ≈ 1 year (no moat) to 10–15+ (wide); trend positive/stable/negative, "stable" = no change expected over several years (S-new-M06-1, pp. 1–2, 4).
2. Advantage has become significantly harder to sustain across industries; lasting advantage comes from a sequence of advantages (S-new-M06-3, abstract).
3. Base fade ≈ 38%/year (Round 1); industry structure outlasts firm effects (S-new-M06-4), so oligopoly evidence supports a longer band.
4. Wide-moat portfolios (Jun 2002–May 2014) beat the S&P 500 and Russell 3000 with positive 4- and 5-factor alphas and smaller 2007–09 losses (S-new-M06-8, abstract). No independent test of ratings predicting ROIC persistence was found. Median TTM ROIC by class — wide 12.5% (n 209), narrow 9.0% (n 643), none 5.1% (n 651) — is a partly circular cross-section, not a prediction test (S-new-M06-18, p. 2).
5. High returns with heavy investment invite faster entry (S-new-M06-2, p. 6) — relevant to MU and NVDA.
6. **Data.** Years above hurdle (`series`); RPO due within 12 months (note text); rung dates (Round 4); share history. Trend: GM/ROIC slope, peer-gap and share change, competition text (DS7), rung moves. Gaps: patent expiry, DS7.

### Worked example
Fade (formula M04 pack S-new-55; our arithmetic): 10 pp excess → ≈ 6.2 pp after 1 year, 2.4 after 3, 0.9 after 5.

| Ticker | Evidence (real) | Proposal (illustrative) |
|---|---|---|
| MSFT | GM 64.0–69.8% FY16–26 as revenue rose $91.2B → $331.8B; dip 69.8 → 67.9 FY24–26 (AI capex depreciation plausible; confirm in MD&A) | ≥ 10 years; stable/watch |
| INTC | GM 61.7% (2018) → 32.7% (2024); operating loss 2024–25 | < 3 years / no moat; negative |

### All cases
1. Long ROIC record + confirmed source + no rung ≥ 3 challenger → ≥ 10 proposal.
2. Long record, no named source → capped at 3–10.
3. Industry-structure evidence + stable/positive trend → eligible for ≥ 20.
4. Short history → no band.
5. One adverse print → "watch"; second consecutive → "negative" proposal.
6. 10-K/10-Q or rung event → re-run; alert (M01 rule 6).
7. No position horizon → asked at entry, stored (D12).
8. Horizon above band low → A3 not met, warning.
9. Cyclical peak → band from the full cycle.
10. Band change → new `as_of`, owner confirms.

### Suggestions
- **S3.1** `moat_duration_band` (< 3, 3–10, ≥ 10, ≥ 20) and `moat_trend` (positive/stable/watch/negative) with evidence and `as_of`.
- **S3.2** Illustrative rule: ≥ 10 needs ROIC > hurdle in ≥ 8 of 10 years (or the cycle), a confirmed source, no challenger at rung ≥ 3; ≥ 20 adds industry-structure evidence and a stable/positive trend. Calibrate on labelled cases.
- **S3.3** A3: `duration_band_low ≥ position.horizon_years`.
- **S3.4** Re-run after each 10-K/10-Q and on rung events.

### Failure modes (rows for M06_MOAT.md)
| Indicator | How it misleads | Guard |
|---|---|---|
| Years point estimate | False precision | Bands with evidence; owner confirms |
| Track-record length | Past ≠ future (S-new-M06-3) | Counts only with a named source |
| Firm AR(1) fit | Noisy on 10–15 points | Info only |
| One-quarter trend | Noise | 2-period rule (as M04 peer z) |
| A3 comparison | MY horizon open (M01) | Position's thesis horizon |

### Questions
**3.1 Duration output**
- (a) *Recommended.* Bands with evidence. Why: no validated model for a point estimate.
- (b) Years as a point estimate.
- (c) Narrow/wide only.

**3.2 MY horizon for A3**
- (a) *Recommended.* Per-position horizon at entry (default 5 years). Why: M01 leaves MY open; A3 needs a number.
- (b) One global horizon.
- (c) 10 years.

**3.3 "Watch" state**
- (a) *Recommended.* Add it. Why: shows a print without calling it confirmed.
- (b) Three states only.

---

## Round 4 — Challenger tracking (R21)

### What the research says
1. Micron announced HBM3E volume production on 2024-02-26; 24GB 8H parts in NVIDIA H200, shipping Q2 2024 — rung 3/4, customer named by the supplier (S-new-M06-13).
2. Samsung (S-new-M06-14): 12H sampling to unnamed customers announced Feb 2024 (release not read); Korean media reported 12H passed NVIDIA qualification in Sep 2025, no confirmation quoted, small initial orders. 8H: Reuters reported clearance 2024-08-07 (Samsung declined to comment); in May 2024 Samsung disputed a report of failed tests. Grade B at best; reversible.
3. CXMT: small-scale HBM3E; T-Head and Cambricon reportedly testing; not qualified; ≈ 25% yield on 8-layer HBM3 (SemiAnalysis); leaders on HBM4 (S27, dated 2026-09-01, not "Aug 2026").
4. Share moves before incumbent margins: Samsung 15% → 21% → 33% (S-new-M06-15).
5. Supplier–customer links are priced slowly (S44); L1 is the strongest free qualification evidence, but 42% of major customers went unnamed in one 1999–2013 sample (S78).
6. Fluidity (S-new-M06-7) is a cross-check only; data end 2023.
7. **Data.** Stored: `supply_link`, news tables (IR RSS = A; Finnhub/Massive/trade = B/C), theme phrases, `theme_first_mention`, EX-99.1 releases (`news/sec8k.py`), EFTS `fulltext_hit`. Foreign challengers file nothing with the SEC → alias keys, `cik` NULL. News is snippet-only (D-M02-2).

### Worked example
| Market | Challenger | Rung | Date | Evidence | Grade |
|---|---|---|---|---|---|
| HBM3E | Micron (vs SK hynix) | 3 + named customer (H200) | 2024-02-26 | Micron release | A (claim) |
| HBM3E 12H | Samsung | 1 sampling | 2024-02 | Samsung release (not read) | A (claim), unverified |
| HBM3E 12H | Samsung | 4 at NVIDIA (reported) | 2025-09 | SamMobile citing Korean press | B |
| HBM | Samsung | share 15 → 33% | Q2 25 → Q2 26 | Counterpoint via Edaily/SamMobile | B |
| HBM3E | CXMT | 2 small-scale | 2026-09-01 | JoongAng citing The Information | B |
| Memory (generation unstated) | Samsung, SK hynix, Micron | L1 relationship | FY2026 | NVIDIA FY2026 10-K (M02_BUILD_LOG test example) | A, not rung-specific |

MU read-out (illustrative): industry — R8 holds; CXMT rung 2, a generation behind. Firm — Samsung reported at rung 4 (B) and +12 pp in a quarter → "watch/negative". Not an exit signal (D16).

### All cases
1. Supplier claims sampling or volume, customer named or not → A for the claim; trust read only at rung 4.
2. Customer's own filing names the challenger for the product (L1) → A, rung 4 confirmed.
3. Customer names supplier without product/generation (NVIDIA 10-K) → relationship only.
4. Press report, company silent (Samsung 8H) → B; needs a second independent source.
5. Company disputes a report → status "disputed", reversible.
6. Rung skipping → earlier rungs missing, not inferred.
7. Qualified with small orders → rung 4 and share tracked separately.
8. Generation drift (CXMT HBM3E vs HBM4) → per-generation events.
9. Non-SEC challenger → alias key, `cik` NULL.
10. Name collision ("Samsung" phones/foundry; "HBM" acronyms; M02_BUILD_LOG part 1 note, M02 L2 guard) → market-scoped phrases; owner confirms.
11. Unnamed "major customer" → B at best unless ≥ 10% or owner-listed.
12. Company both incumbent and challenger (MU in R8; MU vs SK hynix) → event read per role.
13. Share gain without rung news → share input only; challenger stalls → dormant.

### Suggestions
- **S4.1** `m06_challenger`: market, incumbent CIK(s), challenger key, product and generation, rung 1–4, date, evidence, grade, status (candidate/confirmed/rejected/disputed), `discovered_at`; one review item per (market, challenger, rung).
- **S4.2** Rung 4 = qualified at a ≥ 10% customer of the incumbent (ASC 280, S77) or an owner-listed customer. Grades: A if the customer names the challenger; A-for-claim if the supplier names the customer; B press; C rumour.
- **S4.3** Rung phrase finder (M02 guidance-finder pattern) over news, releases and call turns (DS1): sampling; risk/pilot/initial production; volume/mass production, HVM, ramp; qualified, design win, certified. Owner checks hits.
- **S4.4** Rung 3–4 at a major customer → trend "negative" proposal, CvD Q2 "weakening", alert (M01 rule 6); rung 1–2 → "watch".
- **S4.5** Seed markets: HBM (MU vs SK hynix/Samsung/CXMT); x86 server (INTC vs AMD; S36, M04 pack S-new-69); foundry (INTC/GFS vs TSMC); AI accelerators (NVDA vs AVGO/MRVL ASICs; R10).
- **S4.6** Log rung-to-rung durations for Round 3 (Samsung 12H sample → reported qualification ≈ 19 months, once Feb 2024 is verified).

### Failure modes (rows for M06_MOAT.md)
| Indicator | How it misleads | Guard |
|---|---|---|
| Supplier release | Self-interested; sampling is cheap talk | A for the claim only; trust at rung 4 |
| Unconfirmed reports | Reported, then disputed | B; second source to confirm |
| Name matching | Samsung phones; HBM acronyms | Scoped phrases; owner confirms |
| Rung skipping | First item says "volume" | Earlier rungs stay missing |
| Qualification ≠ share | Small initial orders | Tracked separately |
| Generation drift | HBM3E vs HBM4 | Generation per event |

### Questions
**4.1 Who confirms rung events**
- (a) *Recommended.* Owner, from a weekly capped digest (like `m02_link`, 10/week). Why: most evidence is B/C and reversible.
- (b) Auto-confirm grade A; owner sees B/C.
- (c) All automatic.

**4.2 "Major customer"**
- (a) *Recommended.* ≥ 10% customer or owner list per market. Why: customers often go unnamed (S78).
- (b) Any named hyperscaler or OEM.
- (c) Owner per event.

**4.3 B-grade rung-4 report**
- (a) *Recommended.* "Watch" plus warning; "negative" only with a second source or grade A. Why: Samsung shows reversals.
- (b) "Negative" at once.

**4.4 Markets first**
- (a) *Recommended.* HBM, x86 server, foundry, AI accelerators. Why: watchlist exposure.
- (b) Every M02 theme.

---

## Round 5 — Verdict, review and the M11 gate (R1, A3)

### What the research says
1. Morningstar rates by committee, not formula → engine proposes, owner decides (D8) (S-new-M06-1, p. 2).
2. No-moat when a value-destroying threat is likely enough (S-new-M06-1, p. 2) → maps to M04's survival gate and CvD.
3. Moat is evidence of quality, not timing: S-new-M06-8 does not test entry timing. The gate sets eligibility; M08/M09 time entries. (A valuation-overlay claim was dropped pending the Wide Moat Focus Index methodology.)
4. Evidence that ratings predict persistence is thin and vendor-made (Round 3) → the verdict is a judgement with evidence, not a forecast.
5. **Data.** Rounds 1–4 plus M04; writes `signal` (D13, migration 0001) with `module_id = 'M06'` and review items `m06_verdict`, `m06_source`, `m06_rung`. No new external data.

### Worked example
Facts real (S-new-M06-17, Rounds 1 and 4); verdicts illustrative, pending the owner.

| Ticker | Quant leg | Sources | Challengers | Verdict / band / trend | MY gate |
|---|---|---|---|---|---|
| MSFT | GM 64.0–69.8%; ROIC ≈ 36.5% FY26 | Switching, network | — | NARROW or WIDE / ≥ 10 / stable-watch | Pass if confirmed, horizon ≤ 10 |
| INTC | GM 61.7 → 32.7%; operating loss 2024–25 | None confirmed | AMD in server (S36) | NONE / < 3 / negative | Fail (visible; override possible) |
| MU | GM −9.1% (FY23) to 80.7% (FY26) | Efficient scale (R8) | Samsung rung 4 (B); CXMT rung 2 | Ambiguous → review (5.3) | Pending |
| NVDA | GM 56.1 → 75.0% FY16–25, 71.1% FY26 | Switching (software, to evidence), scale | Custom ASICs (R10) | Review | Pending |
| SPCX, INFQ | Too short | — | — | UNRATED | Not met |
| MSTR | Asset vehicle | — | — | N/A | N/A |

### All cases
1. WIDE/NARROW confirmed + band ≥ horizon + survival gate → met.
2. Moat confirmed, band < horizon → not met (A3), warning.
3. Survival gate fails → not met.
4. NONE → fail, visible.
5. UNRATED (short history, M03 type A) → "not met: unrated" + review item.
6. N/A (MSTR, ETV) → never "fail".
7. Ambiguous (MU) → review.
8. Owner override → reason logged (D12).
9. Downgrade, negative trend or rung 4 while held → warning (D16), CvD Q2.
10. No review since last 10-K → stale.
11. Mixed grades → lowest deciding grade.
12. PT/ST → gate optional/none; still visible (D10).

### Suggestions
- **S5.1** MY gate: owner-confirmed `moat_verdict` ∈ {WIDE, NARROW}, `duration_band_low` ≥ horizon, survival gate passes; UNRATED → review; NONE → fail; logged override.
- **S5.2** Warnings only (D16): negative trend, rung 4 at a major customer, downgrade → CvD Q2, and via CvD to M01 rule 4.
- **S5.3** Timeframe parameters:

| Parameter | MY | PT | ST |
|---|---|---|---|
| Gate | Hard (R1), logged override | Optional | None |
| Weight | Lead (M01) | Medium | Low |
| Review | Each 10-K + events | Each 10-Q + events | Events |
| Duration | ≥ thesis horizon (A3) | ≥ 1 year | — |

- **S5.4** Show evidence for and against; blind first look for new names (as M02 gold labels).

### Failure modes (rows for M06_MOAT.md)
| Indicator | How it misleads | Guard |
|---|---|---|
| Hard gate | Excludes a young moat not yet in ROIC | `UNRATED` ≠ `NONE`; logged override |
| Stale verdict | Never revisited | Re-review per 10-K and events; `as_of` |
| Anchoring | Owner confirms by default | For/against evidence; blind look |
| N/A names | MSTR, ETV | `N/A`, never "fail" |
| Grade mixing | B shares look like filing fact | Lowest deciding grade |

### Questions
**5.1 R1 gate in MY**
- (a) *Recommended.* Hard gate, logged override. Why: honours R1, allows documented exceptions.
- (b) Heavy weight, no gate.
- (c) Hard gate, no override.

**5.2 UNRATED names**
- (a) *Recommended.* Not met; owner qualitative verdict allowed, marked "qualitative only, grade B/C". Why: young names stay reachable without a faked record.
- (b) Excluded until 7 years of data.
- (c) Treated as NARROW.

**5.3 Cyclical oligopoly** (MU)
- (a) *Recommended.* Through the cycle: NARROW (efficient scale) if full-cycle median ROIC clears the hurdle, peaks excluded. Why: R8 is structural; margins are cyclical.
- (b) NONE.
- (c) Case by case.

**5.4 Review cadence**
- (a) *Recommended.* Each 10-K plus events. Why: data move yearly, challengers on events.
- (b) Quarterly.
- (c) Events only.

---

## Signals out
D13 records, `module_id = 'M06'`, visible in every timeframe (D10); `evidence_grade` = lowest deciding grade; `method` names the rule and ROIC definition.

| Signal | Type / range | MY | PT | ST |
|---|---|---|---|---|
| `moat_verdict` | WIDE 2 / NARROW 1 / NONE 0 / UNRATED / N_A (NULL value) | Gate (R1) | Weight | Info |
| `moat_duration_band` | < 3 / 3–10 / ≥ 10 / ≥ 20 years | Gate (A3) | Info | Info |
| `moat_trend` | positive / stable / watch / negative | Warning | Warning | Info |
| `challenger_max_rung` | 0–4 per market | Warning | Warning | Info |
| `moat_sources` | confirmed sources | Info | Info | Info |

## Build parts (proposal)
One conversation each at Medium effort, branch `m06-partN`; each updates M06_MOAT.md (and DATA_SOURCES.md) in the same commit with fixture tests; one owner live check per part (`uv run python scripts/run_live.py <label>`, minutes). No new packages expected.

| Part | Contents | Depends on | Live check |
|---|---|---|---|
| 1 Metrics | Concept additions (with M04 part 1); `m06_metrics`; persistence (1.1–1.3) | M04 part 1 | Companyfacts for the 16 names + report of new tags used |
| 2 Sources and shares | `m06_source`; pattern proposals; share form; KPI extractor (DS2/DS14) | 1; M04 part 7 | KPI report over stored EX-99.1 (META, TSLA) |
| 3 Challengers | `m06_challenger`; rung finder; seed markets; weekly digest | M02 part 7 | News refresh + rung-finder report |
| 4 Verdict and gate | Band and trend; verdict, gate, signals, CvD Q2 feed; Moat tab mocked up first (D-UI-4) | 1–3; M04 survival gate | Gate printout for the watchlist |

## Known gaps
- **Unverified:** PatentsView; Li–Lundholm–Minnis word list; Peters & Taylor recipe; Samsung Feb 2024 release; Mauboussin 2024 update (403); Counterpoint's own table; Hoberg–Phillips licence. **Abstract only:** S-new-55, S-new-M06-3, -8, -10; S-new-M06-12 record only.
- **Data:** WACC not free; shares have no API; foreign challengers file nothing with the SEC; customers often unnamed (S78); fluidity needs a gvkey→CIK map (none free) and ends 2023; DS7 (already lists M06); unmapped tags (tax, pretax, current debt, leases, goodwill, NCI, deferred revenue); MSFT RPO not fetched; SPCX/INFQ too short; MSTR/ETV N/A.
- **Proposed DATA_SOURCES.md:** DS16 market shares (B, owner-entered) — gap; DS17 Hoberg–Phillips fluidity/TNIC — gap; user and installed-base KPIs fold into M04 pack DS14.
- **SOURCES.md fixes:** S14 gains URL; S06 extended; S27 date → 2026-09-01.

## New sources
Provisional; next free S-numbers on adoption. "Other" = not peer-reviewed.

- **S-new-M06-1** Morningstar, *Equity Research Methodology* (29 Sep 2022), pp. 1–2, 4 [primary; = S14] — https://indexes.morningstar.com/api/docs/68b1f8066315c9eedeb522fb
- **S-new-M06-2** Mauboussin, Callahan & Majd (1 Nov 2016), "Measuring the Moat", Credit Suisse [other] — https://www.safalniveshak.com/wp-content/uploads/2017/01/Measuring-the-Moat-Mauboussin-2016.pdf
- **S-new-M06-3** Wiggins & Ruefli (2005), "Schumpeter's Ghost: Is Hypercompetition Making the Best of Times Shorter?", *SMJ* 26(10):887–911 — https://ideas.repec.org/a/bla/stratm/v26y2005i10p887-911.html
- **S-new-M06-4** McGahan & Porter (1999), "The Persistence of Shocks to Profitability", *REStat* 81(1):143–153 — https://ideas.repec.org/a/tpr/restat/v81y1999i1p143-153.html
- **S-new-M06-5** Chan, Karceski & Lakonishok (2003), "The Level and Persistence of Growth Rates", *JF* 58(2):643–684 — https://www.lsvasset.com/pdf/research-papers/Level+Persistence_of_Growth_Rates_FINAL.pdf
- **S-new-M06-6** Li, Lundholm & Minnis (2013), "A Measure of Competition Based on 10-K Filings", *JAR* 51(2):399–436 — https://ideas.repec.org/a/bla/joares/v51y2013i2p399-436.html
- **S-new-M06-7** Hoberg, Phillips & Prabhala (2014), "Product Market Threats, Payouts, and Financial Flexibility", *JF* 69(1):293–324; data — https://hobergphillips.tuck.dartmouth.edu/
- **S-new-M06-8** Kanuri & McLeod (2016), wide-moat portfolio performance, *Applied Economics* 48(52):5117–5127 — https://aquila.usm.edu/fac_pubs/17820
- **S-new-M06-9** Novy-Marx (2013), "The Other Side of Value: The Gross Profitability Premium", *JFE* 108(1):1–28 — https://ideas.repec.org/a/eee/jfinec/v108y2013i1p1-28.html
- **S-new-M06-10** Dichev & Tang (2009), "Earnings Volatility and Earnings Predictability", *JAE* 47(1–2):160–181 — https://ideas.repec.org/a/eee/jaecon/v47y2009i1-2p160-181.html
- **S-new-M06-11** Peters & Taylor (2017), "Intangible Capital and the Investment-q Relation", *JFE* 123(2):251–272 — https://ideas.repec.org/a/eee/jfinec/v123y2017i2p251-272.html
- **S-new-M06-12** Katz & Shapiro (1985), "Network Externalities, Competition, and Compatibility", *AER* 75(3):424–440 — https://ideas.repec.org/a/aea/aecrev/v75y1985i3p424-40.html
- **S-new-M06-13** Micron, HBM3E volume production release (2024-02-26) [primary] — https://micron.gcs-web.com/node/46656
- **S-new-M06-14** Samsung HBM3E reports [other]: SamMobile (2025-09-22) — https://www.sammobile.com/news/samsung-may-finally-have-scored-the-nvidia-win-it-desperately-needs/ ; ThePrint/Reuters (2024-08-07) — https://theprint.in/tech/exclusive-samsungs-8-layer-hbm3e-chips-clear-nvidias-tests-for-use-sources-say/2211708/
- **S-new-M06-15** Counterpoint HBM shares Q2 2026 via Edaily (2026-09-03) [other; extends S06] — https://en.edaily.co.kr/news/eda202609035608/ ; SamMobile — https://www.sammobile.com/?p=16676368
- **S-new-M06-16** = S27 with date corrected to 2026-09-01 — https://www.koreajoongangdaily.com/business/chinas-cxmt-begins-hbm3e-production-as-chip-battle-with-korean-powerhouses-widens/12854260
- **S-new-M06-17** SEC XBRL companyconcept, checked 2026-10-12: INTC, MSFT, NVDA, MU gross profit, revenue, operating income; MSFT equity, LT debt, cash & ST investments, tax, pretax income — `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<Tag>.json`
- **S-new-M06-18** Morningstar, "Not All Moats Are Created Equal" (30 May 2017), p. 2 [other; VanEck copy] — https://vaneck.com.au/not-all-moats-are-created-equal
- **Reused:** S06, S14, S27, S36, S41, S44, S77, S78, S79; M04 pack S-new-4, -22, -55, -69.
