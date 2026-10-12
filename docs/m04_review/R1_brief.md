# M04 Round 1 — Data and what is buildable now — brief

**Decides:** how M04 reads its inputs (shares, capex definitions, peers, offsets, capex split; 1.1–1.5) and the company profile and record format later rounds route on (stage, model tags, signal encoding, guidance; 1.6–1.9). New 1.10–1.12: core trends, stage confirmation, the issuance-funded tag's gate.
Changes to approved decisions: A2 default Greenwald → depreciation (1.5a); D13 gains `value_text` (1.8a); R2 "ambiguous stage" rule (1.6a, 1.11); D-M04-1 gate scope by model tag (1.7a, 1.12); D-SEC-9's 45 days split by period type (1.4a).
**Outline items:** Analyze the financials 1–4 (l.65–70); data for Red Flags 1–6 (l.77–83); CAPEX 3–4, growth vs maintenance capex with ROIC (l.92–94); the Micron cyclical example (l.47–53).

## What the research says
- **Most inputs are stored.** `fact` keeps every companyfacts value with accession, form and filed date; F, Z″ and Beneish need no new fetch. Dimensional facts (segments, customer %, multi-class cover counts) are missing (S40, S41, DS12).
- **Two point-in-time defects** (S-new-1): tag priority runs before time (Micron FY2018 revenue, filed 2018-10-15, shows as first filed 2019-10-17), and "latest" has no form filter (Alphabet 2023 net income from a DEF 14A).
- **Concepts that mislead** (S-new-r1-1): `da` gives Intel FY2019 $200M against $9,204M depreciation, and is empty for MSFT and GOOG; `ppe_net` stops for five names; Amazon's FY2016 capex is 15.8% higher on the fallback tag (S100). Shares mix balance-sheet and cover dates; META, MSTR, GOOG and SPCX have no usable count.
- **Peers:** code exists, none stored. SIC 3674 holds solar names and misses QCOM and WDC; GICS fits better but is not free (S-new-2, S110). A 45-day offset leaves 51% overlap for a quarter.
- **Greenwald fails on real data:** out of the 0…capex range in 6 of 8 Micron and 4 of 4 Intel years, because revenue fell (S13). The quoted rule averages yearly PP&E/sales ratios over five prior years (secondary of p. 96); the pack used sums, so its column is recomputed at build.
- **Dickinson signs misroute large caps** (S-new-56; Table 1 unread): Apple reads shake-out from maturing securities, Intel growth from partner financing. The 62%/30% persistence rates are a Brazilian sample.
- **Deadlines are rules** (S-new-r1-3, S88, S-new-r1-4/5): 10-K 60/75/90 days by filer status, 10-Q 40/40/45, 20-F four months, NT +15/+5. Text in the NUMERIC `value` column sorts above every number (S-new-r1-7).

## Worked example
**Sitting 1 — data.** Micron FY2022 → FY2023, the CvD "expect CYCLICAL_TROUGH" case (10-K XBRL; release S-new-5; $M):

| Item | FY2022 | FY2023 | Question |
|---|---|---|---|
| Revenue | 30,758 | 15,540 (−49.5%) | — |
| Gross margin | 45.2% | −9.1% | 1.10 |
| Operating cash flow | 15,181 | 1,559 | — |
| Capex: PP&E tag / company "net capex" | 12,067 | 7,676 / 7,010 stated | 1.2 |
| Depreciation | 7,030 | 7,670 | 1.5 |
| Inventory days, closing (average) inventory | 144.2 | 180.5 (162.0) | — |

Capex split ($M; Greenwald as the pack computed it, recomputed at build):

| Case | Total capex | Greenwald maintenance | Depreciation | 1.5a uses | 1.5b uses | 1.5c uses |
|---|---|---|---|---|---|---|
| MU FY2023 (bust) | 7,676 | 25,285 (3.3× capex) | 7,670 | 7,670 | 7,670 | 25,285 |
| MU FY2026 (boom) | 30,712 | −106,890 | 9,420 | 9,420 | 9,420 | −106,890 |
| INTC 2022 | 24,844 | 36,533 | 11,128 | 11,128 | 11,128 | 36,533 |
| MSFT FY2026 (build-out) | 115,948 | 90,086 (77.7%) | 34,300 (29.6%) | 34,300 | 90,086 | 90,086 |

Greenwald fails whenever revenue falls, under any reading. Inside the range the proxies disagree: Microsoft's owner earnings differ by about $56B. That is a disagreement, not proof; 1.5a rests on the out-of-range years and on capex leading revenue in a build-out. Micron FCF on total capex: FY2023 −$6,117M, FY2025 $1,668M, FY2026 $58,963M; with depreciation as maintenance −$6,111M, $9,245M, $80,255M.

**Sitting 2 — profile and records** (S-new-r1-1, S-new-r1-9, intc.com):

| Name | Total investing (5.1a) | Core investing | Revenue CAGR 3y | 1.6a | With 1.11a |
|---|---|---|---|---|---|
| AAPL | shake-out ×3 | mature ×3 | +1.8% | mature | confirm once |
| INTC | growth ×3 (financing inflows) | same | −5.7% | review: growth, revenue falling | review |
| TSLA | growth ×3 | same | +5.2% | growth, silently | owner confirms |
| NVDA / MU | mature ×3 / mature, mature, growth | same | +100.0% / +104.6% | review: mature, CAGR > 20% | review |
| BA | mature, introduction, shake-out | same | +10.3% | review: no 2 of 3 | review |
| MRVL | mature, mature, shake-out (divestiture) | same | +11.4% | mature | confirm once |
| MSTR | growth, introduction ×2 | same | −1.5% | tag `asset_treasury`; review | review |
| SPCX, INFQ | under one post-event year | — | — | review; both flag sets labelled | review |

META (+19.9%) sits just under 20%. First run: 7 reviews under 1.6a; 15 (every operating name) with 1.11a.

| Guidance case | Guide | Actual | 1.9a | 1.9b | 1.9c |
|---|---|---|---|---|---|
| MU Q3 FY2023 revenue, GAAP GM, EPS | $3.70B ± 0.20; (23.0%) ± 2.5; ($1.79) ± 0.07 | $3,752M; −17.8%; −$1.73 | 3 hits | 3 hits | 3 hits |
| INTC FY2022 revenue | $76.0B (Apr) → $65–68B (Jul) → $63–64B (Oct) | $63,054M | hit; 2 downward revisions | **miss** (< $63.5B midpoint) | **miss** (−17.0%) |
| INTC January 2023 release | Q1 only, as in January 2022 | — | not flagged | **removed** (false) | — |
| INTC April 2023 release | Apr 2022: FY revenue, EPS, capex, adj. FCF; Apr 2023: Q2 only | — | removed; recheck: the January 2023 call reportedly gave the reason, so likely "reason stated" | removed | — |

## All cases
- **Tags:** stable; switch (walk all tags in filed order); broader fallback, marked (AMZN/NVDA capex, MU debt with leases, PP&E with finance leases); extension only (instance read; NVDA FY2013–21); dimensional only ("missing: dimensional"); wrong-meaning tag dropped (INTC).
- **Values:** absent → missing, never zero (reported zero kept); gross profit derived, labelled (AMZN, GOOG, META, SPCX, INFQ); restatement, recast, split (cover counts too); 8-K/DEF 14A/S-1/S-4 values never "latest"; YTD-derived quarters; balance-sheet vs cover dates; before XBRL → "insufficient history".
- **Periods and peers:** 53-week and off-calendar years; peers in or out of tolerance, non-SEC, outside SIC, other business inside SIC, acquisition years (AMD 2022), fallback-tag values, fewer than 5.
- **Entities:** financials and funds excluded unless tagged; non-watchlist names need an owner fetch; delisted → overdue, last state kept (Invitae); foreign issuer (GFS: 6-K XBRL gaps, no 8-K items, IFRS wording); 20-F → 10-K switch; de-SPAC boundary (INFQ); recent IPO (SPCX, no TTM until the first 10-K); transition reports unannualized.
- **Added:** de-SPAC 3.01/4.01 read as red flags (INFQ); stage on short history; only D&A tagged (acquirers); release-silent guiders (MSFT, AAPL, TSLA, BA, SPCX); one guide in several bases (Intel); point and "approx" guides.

**Completeness:** complete for the watchlist, named peers and fixtures once the added cases are in. Omitted: banks and insurers (excluded), 40-F ADRs and pre-2011 restated XBRL (none on the watchlist).

## Suggestions
- **S1.1** `facts_as_of()` from `fact`: periodic forms only, tag priority after time, de-SPAC boundary. *Changed:* all M04 signals, live and backtest, read it; `series` is display only.
- **S1.2** Shares per 1.1; split guard also on cover counts.
- **S1.3** Concept fixes (`da` adds `Depreciation`, drops the nonproduction tag; `ppe_net` marked fallback; GE "Contract assets (pre-ASC 606)" alias) and the extra-tag list.
- **S1.4** Tag and accession on every value; fallbacks visibly marked.
- **S1.5** M04 first writes the D13 table. *Changed:* the signals table is provisional; round tables govern until rebuilt.
- **S1.6** *Changed:* `filing_status` = `overdue` (Round 6 name), Round 1's status-based due dates; backtests derive status from stored public float with Rule 12b-2 thresholds, longest deadline only when float is missing. Invitae FY2023 10-K was due 2024-03-15.
- **S1.7** Guidance per 1.9; one outcome per metric and period; release-silent → "missing (DS1)"; `guidance_removed` event (information) for M01 rule 4.
- **S1.8** Register DS12–DS17; update DS7, DS8.
- **S1.9** Housekeeping; renumber 5.1 → 1.6 and 3.4 tags → 1.7 elsewhere.
- **S1.10** Review kinds: `m04_peer` about 13 at setup; `m04_stage` 7, or 15 with 1.11a (matches S5.14).
- **S1.11** *New:* 8-K sub-classes: 3.01 transfer of listing → information; 4.01 within about 90 days of a de-SPAC closing with no disagreements → information.
- **S1.12** *New:* fetch plan: R1 full history 163 filings (measured).

## Check flags
- Outline Analyze 1–4 (revenue CAGR, FCF growth, margin expansion, operating leverage) have no signal → new 1.10. Red Flags 6 and 1 → Round 3 questions 3.8 and 3.9.
- 1.6a dropped 5.1a's owner confirmation (Tesla assigned silently) → new 1.11. Short history went to "unassigned", against R2 → now review (1.6a). 1.6b was a straw man → restated.
- Tag names and the issuance-funded gate differ across Rounds 1, 3, 6 → 1.7a names everywhere; gate per new 1.12. Tag applies before stage.
- Financials: one definition, FF12 group 11 (as Round 4); untagged excluded names read "not applicable"; engine proposes `reit` for SIC 6798.
- 1.5a dropped A2's D&A rung, and the outline's ROIC pairing had no owner → D&A kept last; M05 owns growth capex × ROIC.
- `value_text` must bind M03, M07, M11 and M12 too → final critic pass.

## Gaps
**Closed now**
- Intel July 2022 release: revenue $65–68B, net capex $27B, adj. FCF ($1–2)B (intc.com, read 2026-10-12): two downward revisions; actual 3.0% below the July low end.
- Greenwald: five prior years, average of yearly ratios (secondary of p. 96; its own example includes the current year). Gross vs net open. 1.5a unchanged.
- Invitae: float at most about $430M at 2023-06-30, under $560M, so accelerated; due 2024-03-15 (Rule 12b-2; shares by search relay, price secondary).
- R1 pages: 163 measured; format verified to 2011 (MSTR Q2 2011).
- INFQ 3.01 (move to NYSE) and 4.01 (SPAC auditor replaced, no disagreements): routine (Infleqtion IR copies).
- Guidance ledger (log 2026-10-08): 31 parsed rows; MSFT, AAPL, TSLA, BA, SPCX guide nothing in releases.
- Stage CAGR line: 20% is the OECD-Eurostat high-growth definition (firm statistics, not stage research); same first run as 25%.
- Micron's oral 153/235 inventory days reproduce on average inventory with write-downs added back.

**Still open:** Dickinson Table 1 (paywalled); ±40 days, "2 misses in 4" and the depreciation cap stay starting values.

**Needs the owner's live probe** (one run, about 11–17 SEC requests; none blocks a question): P1 browse-by-SIC 3674 (5–10) · P2 `uv run python scripts/run_prices.py --symbols NVTA,RAD,JCP,SHLD,FIT` (Tiingo delisted coverage; writes `price_bar` rows) · P3 Invitae dei float (2, optional) · P4 SPCX 10-Q R1 page (1) · P5 NVIDIA capex extension tag (2–4) · P6 GE FY2017 balance-sheet R page (1–2). Local: L1 Greenwald recompute; L2 guidance vs actuals.

## Questions
**Sitting 1 — data (1.1–1.5)**

**1.1 Shares concepts**
- (a) (recommended) Period-end, cover, basic and diluted weighted-average series plus `sbc`; multi-class cover counts from R1 pages; float shares = public float ÷ Q2-end close, "implied". Why: fixes four silent gaps; gives M07 a float. Gets wrong: costs 1 request per new multi-class filing.
- (b) Multi-class names use basic weighted average. Gets wrong: MSTR cover +35.5% vs weighted +28.1%.
- (c) One series plus diluted. Gets wrong: Apple stays mixed; diluted moves with the profit sign.

**1.2 Capex definitions**
- (a) (recommended) Display the company's definition with the tag value and a visible "≈ broader tag" marker; own history on the longest consistent tag; peers on the PP&E tag only. Why: Amazon's same year differs 15.8% by tag. Gets wrong: AMZN and NVDA have no peer leg.
- (b) Fallback values in peer statistics. Gets wrong: AMZN/NVDA about 16% high in the median.
- (c) A row per tag. Gets wrong: Amazon's PP&E row empty after FY2016.
- (d) Tooltip only. Gets wrong: the broader definition stays hidden.

**1.3 Peer discovery**
- (a) (recommended) Propose from 4-digit SIC plus a browse-by-SIC probe; owner confirms and adds product peers (QCOM, WDC); non-SEC peers "missing". Why: R24, no bulk file. Gets wrong: solar names proposed until removed.
- (b) 3-digit SIC. Gets wrong: adds component makers, still misses QCOM and WDC.
- (c) Owner lists only. Gets wrong: new entrants never surface.
- (d) Bulk submissions.zip. Gets wrong: about 2 GB per refresh.

**1.4 Peer period offset**
- (a) (recommended) TTM ±45 days; quarters and instants ±40; end dates shown; 53-week years flagged. Why: keeps WDC (29–36 days), stops two-month gaps. Gets wrong: a quarter can still overlap only 56%.
- (b) Quarters ±35. Gets wrong: WDC drops out for two quarters.
- (c) Quarters ±16 with a calendar fallback. Gets wrong: MU–WDC never matches directly.
- (d) ±45 for all. Gets wrong: 51% quarter overlap.

**1.5 Capex split (A2)**
- (a) (recommended) M04 owns `capex_split`: disclosed → project-level → depreciation (capped at capex) → D&A, marked → "not split"; Greenwald beside it when in range; consumers use total capex; owner earnings information; M05 owns growth capex × ROIC. Why: Greenwald out of range in 6 of 8 Micron, 4 of 4 Intel years. Gets wrong: useful-life changes move depreciation (Intel 2023 −29.5%).
- (b) Greenwald where in range, else depreciation. Gets wrong: Microsoft's build-out read as $90,086M maintenance.
- (c) Approved ladder as written. Gets wrong: Micron FY2023 maintenance 3.3× capex; FY2026 negative.
- (d) M05 owns A2. Gets wrong: no owner earnings until M05.

**Sitting 2 — company profile and records (1.6–1.12)**

**1.6 Life-cycle stage** (replaces 5.1)
- (a) (recommended) Dickinson signs on core investing, 2 of 3 years. Review when no 2 of 3, held stage shake-out, or a CAGR conflict (growth below 0%, mature above 20%). Under 3 years → review, both flag sets labelled, uncounted. Why: total investing misreads Apple and Intel. Gets wrong: MRVL's latest-year shake-out not reviewed.
- (b) 5.1a in full (total investing; owner confirms). Gets wrong: Apple a review item every year.
- (c) Owner sets every stage. Gets wrong: BA's changes go unnoticed.
- (d) Growth and cash-flow rules. Gets wrong: NVDA and MU read "young".

**1.7 Owner model tags**
- (a) (recommended) Six tags in hand-edited `config/company_models.toml` (`issuance_funded`, `asset_treasury`, `reit`, `fund`, `financial`, `spac_shell`), with reason and source; tag overrides SIC and applies before stage. Why: MSTR's $5,444M operating loss is almost all bitcoin ($5,403M), and SIC would exclude it. Gets wrong: an untagged treasury company routes by SIC.
- (b) Free-text tags, routing in code. Gets wrong: like cases route differently.
- (c) Two tags plus SIC. Gets wrong: MSTR excluded; SPAC-era INFQ passes as operating.

**1.8 Signal record encoding**
- (a) (recommended) `value_text` for enums, binding all modules; missing = "missing: <reason>" row; one row per timeframe; grade = weakest input; `source_ref` = newest accession. Why: readable, no mixed types. Gets wrong: one migration for all modules.
- (b) Integer codes. Gets wrong: a code change rewrites history.
- (c) Text in `value`. Gets wrong: text sorts above numbers.
- (d) MY rows only. Gets wrong: no place for PT parameters (D12).

**1.9 Guidance record**
- (a) (recommended) Miss = below the latest range's low end, on the guide's basis; point and "approx" guides unscored until a tolerance exists; 2 misses in 4 = repeated; "removed" vs a year earlier, reason checked in the current and prior release and call. Why: R19 without seasonal false removals. Gets wrong: Intel FY2022 a "hit" despite two cuts (counted separately).
- (b) Midpoint; previous release. Gets wrong: Intel FY2022 an in-range miss; January 2023 flagged.
- (c) First guide. Gets wrong: Intel FY2022 a 17.0% miss after two cuts.
- (d) Defer to M11. Gets wrong: the Q2 row stays missing.

**1.10 Core financial trends** (new; outline Analyze 1–4)
- (a) (recommended) Information rows now: `rev_yoy`, `rev_cagr3`, `fcf_growth` (total-capex and owner-earnings bases), `gm_trend_pp`, `opex_vs_sales`; own history and peer z; weights at Part 8 calibration. Why: FCF growth is the outline's golden indicator. Gets wrong: no vote until calibrated.
- (b) Votes now on starting cut-offs. Gets wrong: unsourced thresholds vote.
- (c) Only the approved revenue-vs-peers row. Gets wrong: Micron's FCF $1,668M → $58,963M build-out never shows.

**1.11 Confirm auto-assigned stages?** (new)
- (a) (recommended) Owner confirms each name's first stage once (15 items), then changes and ambiguous cases. Why: Tesla's financing-driven "growth" otherwise escapes the CFO/NI warning. Gets wrong: a one-off batch.
- (b) No confirmation. Gets wrong: Tesla routed as growth silently.

**1.12 `issuance_funded` tag: gate and dilution** (new; governs 3.4)
- (a) (recommended) Normal gate; dilution is review only while the gate passes and runway is outside the warn band, otherwise `financing_pressure` warns. Why: Red Flag 2 is dilution "to survive". Gets wrong: a funded plan in a brief warn band warns.
- (b) Dilution always review (1.7a as drafted). Gets wrong: dilution to survive is only a review item.
- (c) Liquidity-only gate. Gets wrong: burn and runway of a RIVN-like firm never tested.
