# M03 — Leaders & S-curve

Status: MVP design decided 2026-10-21 (sitting 3, D-M03-1…8, every recommended option; M01 weights amendment D-M01-8); Part 1 next (wave W6) · Updated: 2026-10-21 · Outline headings: Catch the S-curve early (items 1, 3); Identify the leaders (items 1, 3) · Depends on: M00 (`fact`, `fact_dim`, `frame_value`, signals), M02 (themes), M04 (stage, peers, 7a instances, 8a `cvd_state` and `market_share`) · Sources: S01, S93, S-new-M03-n (pack; numbered into SOURCES.md at Part 1)

Research: `docs/M03_DESIGN_PACK.md`; MVP cut and sitting record: `docs/mvp/M03_MVP_BRIEF.md`; cross-module plan: `docs/mvp/MVP_PLAN.md`. Thresholds marked † are starting values, never tuned on the watchlist alone (D32). Missing data stays missing (`method` = "missing: <reason>"), never zero (D-M04-9). Research signals, not financial advice.

## Purpose
Where each revenue curve sits on its S-curve, and which curve leads its category. Binding: R6 (type A, a young company on its first curve; type B, a new curve inside an established company, from segment data), R14 (Bessembinder stated as dollar wealth, not returns), D8, D9, D10, D13/D14, D16, D-M02-3 (no blended score). Owned elsewhere: latency before appreciation → M11 (R4 milestones); positioning before the crowd → M02 crowding flag (D-M02-10) and M08; product competitiveness, roadmaps, switching costs → M06. No TAM (no free source, S93; DS22).

## Inputs
| Data | Source (stored in; code) | Grade | Refresh |
|---|---|---|---|
| Segment / product revenue and operating income, 3 years of 10-K/10-Q instances (core + promoted) | `fact_dim` (0035); `sec/instance_dim.py`, `financials/units_view.py` `segment_table()`, `renames()` | A | Per new filing |
| Company revenue (from 2009) | `fact`, `financials/capex.py` `fy_points` | A | Same |
| Confirmed firm stage | `company_stage` (0032) | Owner / A | On confirmation |
| Model tags, shell boundary | `config/company_models.toml`, `entity_link` | Owner | On edit |
| Themes, peers | `theme`, `theme_company`, `tier_member`; `peer_member`, `financials/peer_facts.py` | A / owner | Per M02 / M04 run |
| CvD state, market share | `signal` (`cvd_state`, M04 8a); `market_share` (0039, owner entries, DS16) | per M04 | Per M04 run |
| All-filer CY revenue (median growth) | `frame_value`, `sec/frames.py` (CY2024–25 stored; CY2019–23 fetched once in Part 2, D-SEC-32) | A | 30 days |
| Curve map | `config/m03_curves.toml` (owner-edited, D-M03-2) | Owner | On edit |

## Signals out
Every row: `cik` key (ticker for display), `module_id = "M03"`, one row per timeframe, number in `value`, state in `value_text`, `as_of` = filing date of the newest deciding annual report, `source_ref` = newest accession "+N", inputs in `method`, grade = weakest deciding input (D-M04-9). The curve label is part of the signal name (D-M03-8).

| Signal | value / value_text | Meaning | MY | PT | ST | Grade |
|---|---|---|---|---|---|---|
| `curve_type.<label>` | % of company revenue; A / B / n_a / unassigned | R6 type (D-M03-5) | info | info | info | A; B when the owner sets a type with no filing input |
| `curve_stage.<label>` | latest FY growth %; emerging / accelerating / steep / past_inflection / declining / not_identified | Position on the curve (D-M03-4) | ✓ medium until calibrated (D-M01-8) | info | info | A |
| `leader_rank.<label>` | rank; "k of n with data" | Dollar rank in the owner's category; growth gap to the category median in `method`; M04 `market_share_chg_pp` beside it (D-M03-3) | ✓ (same) | info | info | A; "among SEC filers" when a peer does not file |
| `growth_runs.<label>` | years; `at_least` when the run reaches the start of history | Consecutive years above the all-filer median growth; CKL baselines in `method` (D-M03-6) | ✓ (same) | info | info | A |

Shown with the signals (no D13 rows): every disclosed segment of every covered company with revenue, growth, increment and share of company revenue (D32, D-M03-2); unmapped segments; the "Open for the owner" list; the R14 base-rate card (D-M03-7).

## Timeframe parameters
| Parameter | MY | PT | ST |
|---|---|---|---|
| Role | stage, rank and runs weigh "medium until calibrated" | info until M01 builds PT profiles | info |
| Period | fiscal years (no quarterly TTM in the MVP) | — | — |

## Rules
1. **Curve source** (D-M03-1): a mapped segment or product member from `fact_dim`, or "company" (whole-company revenue from `fact`), axis labelled. Tracked names and peers only as whole-company curves.
2. **Series** (D-M03-4): fiscal-year revenue and dollar increment; a changed segment set is a break and the series restarts (never merged, D-M04-42); a renamed member with agreeing values continues (`renames()`); the latest filing wins within its 3 years, first-filed value on hover; shell periods (`entity_link`) left out.
3. **External revenue** (default kept at sitting 3): where intersegment revenue is disclosed, stage on external revenue and flag "captive" below 50%† external; else total, "external unknown".
4. **Stage** (D-M03-4), cases in order of precedence declining > past_inflection > emerging > accelerating > steep:
   - fewer than 3 fiscal years or a new segment → `not_identified`;
   - `emerging`: curve < 10%† of company revenue or first disclosed < 3 years ago, and growth > 40%†;
   - `steep`: increment rising, growth falling;
   - `accelerating`: increment and growth rising, noted "new curve or cycle?" with the stored `cvd_state`;
   - one year below the increment peak → no change (prior stage holds; none → `not_identified`);
   - `past_inflection`: ≥ 2 years below the increment peak **and** the latest increment not rising (default kept at sitting 3; AWS 2024–25 read `accelerating`);
   - `declining`: revenue below its prior peak ≥ 2 fiscal years; under CYCLICAL_TROUGH it reads "held: cycle";
   - a changed stage is labelled "first reading" until the next year agrees; an acquisition year is marked, not staged.
5. **Type** (D-M03-5): A = curve ≥ 50% of revenue and confirmed M04 stage introduction or growth; B = curve < 50% and confirmed stage mature, shake_out or decline; n_a = fund, treasury-asset or shell periods; else unassigned; owner override in the curve file.
6. **Rank** (D-M03-3): dollar rank of the latest fiscal-year curve revenue among the curves in the owner's category with data; needs ≥ 2 curves with data, else "missing: k of n with data"; non-SEC peers → "among SEC filers".
7. **Runs** (D-M03-6): consecutive fiscal years with curve growth above the all-filer median (revenue > 0 in both years, robust to scaling errors); segment runs labelled indicative.

## Failure modes
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Deceleration | read as maturity | stage needs an increment peak |
| One-year pause | read as the inflection | the not-rising clause |
| Captive revenue | read as a market curve | external revenue and the captive flag |
| Recast segment set | read as growth | breaks; never merged |
| Watchlist of winners | survivorship | the R14 card |
| CKL baselines | US 1951–1998 | labelled "indicative" |
| HBM inside CMBU | invisible in facts | owner shares (DS16) or text at tuning; "missing: not disclosed as a fact" |
| **D32: stage rules derived from tech curves only** (AWS, NVDA, Intel) | price-driven cycles (memory, autos, commodities) can fire `past_inflection` / `declining` | `cvd_state` note; non-tech synthetic fixtures at build (a flat mature consumer segment, a pharma patent cliff); checked on non-tech names at tuning |
| **D32: `emerging` cut-offs** (10%, 40%) | starting values from tech examples | †, calibrated at tuning |
| **D32: captive 50%** | from one company (Intel Foundry) | †, shown with the external share |
| All-filer median | includes micro-caps and SPACs, may sit low | labelled; calibrated later |
| Short history | 3-year filing window ≈ 5 fiscal years, 3 after a break | `at_least`, `not_identified` |
| Unassigned types | 8 names until their M04 stage is confirmed | listed on the tab |

## Decisions
- D-M03-1 (2026-10-21, sitting 3, Q03.1a): curves come from `fact_dim` as stored (core and promoted, about 5 fiscal years); tracked names and peers enter as whole-company curves only; no new requests. The owner may promote AMD or ALAB in the UI as RIVN was (D-M02-11, D-M04-81; about 25 requests plus about 12 instance reads each, once). Why: the stored years already cover AWS, NVDA, INTC and MU (D-M04-42, -80).
- D-M03-2 (2026-10-21, Q03.2a + the D32 default): an owner-edited `config/m03_curves.toml` (ticker, member or "company", label, category, optional type) maps curves; the app never writes it. No review items: ambiguous readings (unassigned types, "new curve or cycle?") go to an "Open for the owner" list on the tab, answered in the file (D8's queue in MVP form). Every disclosed segment of every covered company is shown with revenue, growth, increment and share, mapped or not; mapping only chooses curves (D10, D32). Why: the `company_models.toml` pattern (D-M04-8) with no queue load.
- D-M03-3 (2026-10-21, Q03.3a): a category is owner-named per curve inside an M02 theme (default: the theme); a segment in two categories is two entries, overlap shown. Why: AI infrastructure mixes chips and cloud, so a rank there would compare different layers.
- D-M03-4 (2026-10-21, Q03.4a + the two defaults): stage by rules on fiscal-year increment and growth (rule 4), no K fit; a change is labelled "first reading" until the next year agrees; `maturing` deferred. Kept defaults: the not-rising clause for `past_inflection` and external-revenue staging with the 50%† captive flag. Why: K is biased before the inflection (S-new-M03-11, -12) and fiscal years avoid lumpy quarters.
- D-M03-5 (2026-10-21, Q03.5a): type per rule 5, owner override in the curve file. Why: listing age misleads (SPCX, SPAC CIKs); R6's "established company" needs the confirmed stage (AMZN mature → AWS B).
- D-M03-6 (2026-10-21, Q03.6a): `growth_runs` against the all-filer median from the CY frames (about 10–15 requests once in Part 2, re-used 30 days, D-SEC-32), CKL baselines shown (S-new-M03-4). Why: CKL's baselines are all-firm medians; a segment is not a firm, so segment runs are labelled indicative.
- D-M03-7 (2026-10-21, Q03.7a): an R14 base-rate card on the tab, a paraphrase of S01 (dollar wealth above T-bills, not a return forecast); `wealth_created` deferred. Why: states R14 exactly with no new source.
- D-M03-8 (2026-10-21, Q03.8a; **D-M01-8**): the curve label goes in the signal name (`curve_stage.aws`), no schema change; MY ✓ at "medium until calibrated" in M01's weights row, PT and ST info. M01 and the confluence readers read the prefix before the dot as the signal family. Why: fits D13 as built; thresholds uncalibrated.

## Deferred to tuning
Curve proposals (S1.2), FSN and older instances (S1.5), basis detector (S1.4), components c/d and S2.4 (M04 `gm_trend_pp`, DS16), pioneer tags (S2.3), `maturing` and quarterly TTM (S3.1), K interval (S3.3), unit curves and adoption (S3.5), calibration including failed curves (S3.6, S3.3, S4.3), `wealth_created` (S4.1), tenure (S4.3, S4.4), tier caps and PT alerts (M11 sitting), SOURCES fixes (S4.5).

## Build parts
**Part 1 — Curves** (wave W6; branch `m03-part1`; no migration expected; D-UI-41; DS22 market-size gap row; decisions from D-M03-9). Code: `src/engine/leaders/` `curves.py` (map loader; series with breaks, recasts, captive flag, shell boundary), `stage.py`, `views.py`, `step.py` (local refresh pass, 0 requests, after M05 and M06 in the MVP_PLAN order); company curves reuse `fy_points`, `entity_link` / tags and `segment_table()`'s break and rename logic. UI: "Leaders & curve" tab (`tabs/m03.html`): all segments (D32), the curve table, unmapped candidates, the open list, the R14 card. Live check: `uv run python scripts/run_leaders.py curves --no-sec` (0 requests, under a minute). Fixtures: AWS 2021–25, NVDA Data Center FY2024–26, Intel Foundry (total and external), the MU segment-set break, the BA rename, the INFQ boundary, and D32 non-tech synthetic cases (a flat mature consumer segment; a pharma product past its patent cliff) — real instances need an owner probe, else labelled synthetic `fact_dim` rows on published figures.

**Part 2 — Leaders and persistence** (wave W7; branch `m03-part2`; D-SEC-32 CY frames 2019–23; D-UI-43 theme leader table). Code: `leaders/rank.py`, `leaders/runs.py`. UI: leader table per category on the theme page, rows on the M03 tab, M04's `market_share_chg_pp` beside the rank (else "missing: no share data"). Live check: `uv run python scripts/run_leaders.py leaders` (about 10–15 frame requests the first time), then `--no-sec`.

## Live checks (owner runs, sends the log)
- Part 1: `uv run python scripts/run_leaders.py curves --no-sec`.
- Part 2: `uv run python scripts/run_leaders.py leaders`.

## Open questions
- Google Cloud and Azure dollar figures and NVDA's Data Center axis: checked at Part 1 (leader rows may read "missing" more often than expected).
- INFQ: the shell boundary excludes the operating company's own prior-year comparatives, so its stage waits about 2 years unless the owner sets a series start.
