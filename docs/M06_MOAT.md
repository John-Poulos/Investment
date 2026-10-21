# M06 — Moat

Status: MVP design decided 2026-10-21 (sitting 3, D-M06-1…8, every recommended option; M01 rule-1 amendment D-M01-9); Part 1 next (wave W6) · Updated: 2026-10-21 · Outline headings: Moat Check (items 1–5); Identify the leaders (item 2, switching costs and share) · Depends on: M00 (`fact`, signals, news), M04 (ROIC inputs and `roic_series`, gross margin, peers, tags, 8a `cvd.py` and `market_share`), M02 (news, aliases) · Sources: S06, S14, S27, S36, S77, S78, S224, S-new-55, S-new-M06-n (pack; numbered into SOURCES.md at Part 1)

Research: `docs/M06_DESIGN_PACK.md`; MVP cut and sitting record: `docs/mvp/M06_MVP_BRIEF.md`; cross-module plan: `docs/mvp/MVP_PLAN.md`. Thresholds marked † are starting values, never tuned on the watchlist alone (D32). Missing data stays missing, never zero (D-M04-9). Research signals, not financial advice.

## Purpose
Per equity: is there a moat, from which source, will it outlast the horizon, and is a named challenger catching up? Fills M04 CvD's Q2 row "Moat and challengers (M06)". Binding: R1 (invest only with a moat: the MY gate), R8 (HBM three-supplier oligopoly), A3 (moat duration ≥ timeframe), R21 (challenger rungs: sampling → small-scale → volume → qualified at a major customer; buyer trust read at qualification), R10 (AVGO–Google confirmed, AMD–Google grade C), D8, D13, D14, D16, D21/D28. Departs from the pack: the outline's 3-year catch-up test replaces Morningstar's 10/20-year bands (D-M06-3), and "vertical integration" is a source label (D-M06-4).

## Inputs
| Data | Source (stored in; code) | Grade | Refresh |
|---|---|---|---|
| ROIC per fiscal year (10 years, so 11 balance sheets) | `financials/trends.py` `roic_series` (D-M04-107), `roic_inputs`, `roic` | A | Per new 10-K |
| Gross and operating margin; peer GM z | `trends._gross` (derived where untagged, labelled); `financials/peer_z.py` on confirmed peers | A | Same |
| Model tags (fund, financial, reit, asset_treasury, spac_shell) | `config/company_models.toml`, `financials/models.py` `route` | Owner | On edit |
| Switching-cost evidence (shown, not scored) | `rpo`, `contract_liabilities`, confirmed `supply_link` L1–L3 quotes, `fact_dim` ≥ 10% customers | A | Per filing |
| Market share | `market_share` (0039, owner entries, D-M04-68, DS16) | A / B | On entry |
| Challenger hints | `news_item` / `news_company` / `news_theme` snippets; `config/aliases.toml` (non-SEC challengers matched by alias text; CXMT alias added in Part 2) | B / C | Per news run |
| Owner verdicts and challenger events | `m06_verdict` (Part 1, 0043), `m06_challenger` (Part 2, 0044) | B, or A with a verified filing quote | On entry |
| Config | `config/moat.toml` (hurdle, horizon) | Owner | On edit |

## Signals out
`module_id = "M06"`, keyed by `cik`, one row per timeframe; states in `value_text`; missing = "missing: <reason>".

| Signal | value / value_text | Meaning | MY | PT | ST | Grade |
|---|---|---|---|---|---|---|
| `moat_quant` | share of window years with ROIC > hurdle (0–1); persistent / through_cycle / weak / short_history / not_meaningful / not_applicable | Computed evidence leg | ✓ | ✓ | info | A; `source_ref` newest 10-K "+N" |
| `moat_verdict` | NULL; WIDE / NARROW / NONE / UNRATED / N_A | Owner-confirmed verdict (D8); sources, catch-up band, reason, date in `method`. M06's one confluence vote | ✓ | ✓ | info | owner entry B, or A with a verified stored filing passage |
| `challenger_max_rung` | 0–4; none / watch / warning | Highest R21 rung of a named challenger, per market in `method` | ✓ warn | ✓ warn | info | grade of the deciding event; "warning" needs A or two independent B |
| `moat_gate` | met / not_met / unrated / not_applicable | R1 + A3 eligibility for a first MY entry (D-M01-9) | ✓ gate | info | info | = verdict grade |

Shown with the signals (no D13 rows, D32): 10-year ROIC, gross margin and operating margin for every company, N_A ones included (labelled, e.g. "asset vehicle: ROIC shown, not rated"; "missing: gross profit untagged").

## Timeframe parameters
| Parameter | MY | PT | ST |
|---|---|---|---|
| Horizon for A3 | 5 years, global default in `config/moat.toml` (D-M06-6) | any band above 3 years exceeds it (info) | info |
| Gate | binding for a first entry (R1, D-M01-9) | info | info |

## Rules
1. **Quant leg** (D-M06-2): the last 10 fiscal years with a computable ROIC (7–9 → "short window"; < 7 → `short_history`). persistent = ROIC > 8%† in ≥ 80%† of years; `through_cycle` = below that, but the window median > hurdle **and** ≥ 1 of the last 3 years above it; else weak. Average invested capital ≤ 0 in most years → `not_meaningful`. Tags fund, financial (incl. untagged FF12 financials via `models.route`), reit, asset_treasury and spac_shell periods → `not_applicable`; `issuance_funded` is computed. ±2 pp around the hurdle in `method` (D-M06-1).
2. **Verdict** (D-M06-3, -4, -5): engine proposes (persistent / through_cycle with no warning → NARROW candidate; weak → NONE; short_history → UNRATED; tag → N_A); the owner enters verdict, source label(s), catch-up band (≤ 3 / 3–5 / 5–10 / > 10 years) and a reason. Band ≤ 3 = NONE (outline Moat 5), 3–10 = NARROW, > 10 = WIDE. A cited passage is verified mechanically (D21); unverified → rejected, stored.
3. **Challengers** (D-M06-7): rung per R21; rung 4 = qualified at a ≥ 10% customer of the incumbent (ASC 280, S77) or an owner-listed customer. Rung 1–2, or rung 4 on one B source → watch; rung 3–4 with A or two independent B → warning (never blocking, D16) and "re-check band" on the verdict. Disputed reports are stored, not counted. M01 sees challengers only through `cvd_state`.
4. **Gate** (D-M06-5, -6, D-M01-9): met = NARROW / WIDE and band low ≥ the MY horizon (A3); UNRATED → unrated (not met); NONE → not_met, shown; N_A → not_applicable, never "fail"; owner override logged with its reason and shown as "override" (D12). The survival gate is not repeated (M01 rule 1 already requires it, D-M01-6).
5. **CvD feed** (Part 2; D-M04-1 row, binding): weakening = rung 4 at a major customer with A or two independent B, or an owner downgrade of the verdict; intact = NARROW / WIDE, not downgraded, no such rung 4; else missing (leaves the denominator, D-M04-56). A rung-3 warning stays an M06 warning and does not vote in CvD.
6. **Review cadence** (D-M06-8): one setup batch; then re-open only on a quant-class change at a new 10-K or a challenger warning; otherwise "stale since <date>".

## Failure modes
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Peak margins (MU FY2026 80.7% GM, 106.7% ROIC) | a cycle peak read as a moat | years counted plus the median, never the latest year alone |
| Book ROIC | leases unmapped, R&D expensed, goodwill, buybacks shrink invested capital | "excludes leases"; R&D-heavy label; IC ≤ 0 → `not_meaningful`; acquisition flag beside |
| 8% hurdle | a convention, not a WACC; names within ±2 pp (TSLA 8.1%, GFS 8.3%, MRVL 7.1%) can flip class | ±2 pp shown in `method` |
| Owner verdicts | judgement, grade B; anchoring on the proposal | evidence for and against on the card; verified quotes lift to A |
| Challenger evidence | mostly press, reversible, unnamed customers (S78), name collisions | grades, disputed status, hints never auto-entered |
| Segment moats (AWS inside AMZN) | invisible in consolidated ROIC | "consolidated only" |
| **D32: R8** | one industry (HBM) | "efficient scale" elsewhere stands on its own evidence |
| **D32: seed challenger markets** | all four are semiconductors | events can be entered in any market |
| **D32: `through_cycle`** | built for MU's memory cycle; elsewhere one boom can lift the median | the last-3-years guard; checked on non-tech cyclicals (BA, autos) at tuning |
| **D32: book ROIC for asset-light and financial firms** | misreads chip designers; meaningless for banks and insurers | R&D-heavy label; financial tags → N_A. The 8% hurdle and 80% share come from all-industry studies (fade ≈ 38%/yr, S-new-55), not tech |
| One global horizon | positions differ | per-position horizons with M11 |

## Decisions
- D-M06-1 (2026-10-21, sitting 3, Q06.1a): ROIC hurdle fixed at 8%† after tax, ±2 pp shown in `method`. Why: transparent; no free WACC exists (S14).
- D-M06-2 (2026-10-21, Q06.2a + the two defaults): quant leg per rule 1 (10 years, ≥ 7 needed, persistent ≥ 80%†, the median plus last-3-years guard). The class is named **`through_cycle`** (MVP_PLAN item 5: M08 owns the company-level "cyclical" flag, D-M08-3; M04 owns CvD). The 10-year ROIC, gross margin and operating margin are shown for every company, N_A included (D32). Why: fade ≈ 38%/yr makes years, not level, the evidence (S-new-55); the median keeps R8 names like MU from failing on troughs; the guard keeps INTC's decline out of `through_cycle` (engine FY2025 ROIC −1.1%).
- D-M06-3 (2026-10-21, Q06.3a): duration by the outline's test, an owner-entered catch-up band ≤ 3 / 3–5 / 5–10 / > 10 years; ≤ 3 = NONE, 3–10 = NARROW, > 10 = WIDE. Why: follows outline Moat 5 and gives A3 a number.
- D-M06-4 (2026-10-21, Q06.4a): source labels = Morningstar's five (intangibles, switching costs, network, cost advantage, efficient scale) plus "vertical integration" (outline Moat 2, e.g. CUDA); several labels per verdict allowed. Why: the outline names vertical integration; the five cover the rest (S-new-M06-1).
- D-M06-5 (2026-10-21, Q06.5a): a logged owner override of the gate is allowed; UNRATED = not met, but the owner may enter a qualitative verdict marked grade B. Why: documented exceptions; young names (SPCX, RIVN) stay reachable without a faked record.
- D-M06-6 (2026-10-21, Q06.6a): one global MY horizon of 5 years in `config/moat.toml`; per-position horizons arrive with M11. Why: M01 leaves MY open and `position` has no horizon column.
- D-M06-7 (2026-10-21, Q06.7a): owner-entered challenger events with 4 seed markets — HBM (MU vs SK hynix, Samsung, CXMT), x86 server (INTC vs AMD), foundry (INTC / GFS vs TSMC), AI accelerators (NVDA vs AVGO / MRVL ASICs, R10) — events allowed in any other market; stored news headlines listed as hints. Why: evidence is mostly B and reversible (S-new-M06-14); customers often unnamed (S78). D32: the seeds are all semiconductors.
- D-M06-8 (2026-10-21, Q06.8a): one setup batch of 15 verdict items (17 covered minus ETV and MSTR); afterwards a verdict re-opens only when a new 10-K changes the quant class or a challenger warning is entered; others show "stale since <date>". Why: data move yearly and challengers on events; keeps the queue small.
- **D-M01-9** (recorded in `docs/M01_TIMEFRAMES.md`): M01 rule 1's first MY entry also needs `moat_gate` = met (R1, A3).

## Deferred to tuning
`m06_metrics` table and turnover labels (S1.1, S1.3); R&D-capitalised and goodwill-free ROIC (Q1.2); full-cycle window on D-M04-83 dates (Q1.3); `m06_source`, pattern proposals and Gemini hints (S2.1–S2.3); separate industry and firm ratings (Q2.3); IP / patent evidence (PatentsView unverified); competition text and fluidity (S2.5; DS7, DS21); KPI extractor (S2.6; DS14, DS1); `moat_trend`, cadence and fade fits (R3); per-position horizon (M11); rung phrase finder, durations and a digest (S4.3, S4.6, Q4.1); blind first look and PT/ST gate variants (S5.3, S5.4); SOURCES fixes (S14 URL, S06, S27 date).

## Build parts
**Part 1 — Quant leg, verdict, gate** (wave W6; branch `m06-part1`; migration `0043_m06_verdict`; D-STO-33; D-UI-40; DS21 row; decisions from D-M06-9). Code: `src/engine/moat/` `quant.py` (reuses `trends.roic_series`, `_gross`, `peer_z`), `verdict.py`, `gate.py`, `step.py` (local refresh pass after M05, before M03; 0 requests); `scripts/run_moat.py`; `config/moat.toml`. Table `m06_verdict` (cik, verdict, sources, band, reason, passage ref, grade, override, decided_at, as_of). Review kind `m06_verdict` (setup batch; outside M04's cap). UI: "Moat" section on the Financials tab (10-year ROIC / GM / OM for every company, class, verdict card with RPO, contract liabilities, confirmed supply links); verdict form on a setup page beside `/m04/setup`; mock-up first on MSFT / INTC / MU (D-UI-4). Live check: `uv run python scripts/run_moat.py quant` (0 requests, under a minute; one row per company, 15 setup items). Fixtures: MSFT FY2025–26 (engine 35.9% with current debt), INTC 2021–25 OI (weak only through the guard), MU FY2023 / FY2026 GM, a 6-year company, MSTR / ETV, an IC ≤ 0 year, and a D32 non-tech case (BA-like industrial with losses then one good year).

**Part 2 — Challengers and the CvD feed** (wave W7; branch `m06-part2`; migration `0044_m06_challenger`; D-STO-34; D-UI-42; next free D-M04 for the `cvd.py` hook). Code: `moat/challengers.py` (events, rung logic, news hints by market phrase plus alias); hook in M04 8a `cvd.py` replacing "not applicable until M06" (rule 5); a CXMT line in `config/aliases.toml`. Table `m06_challenger` (market, incumbent cik, challenger key / cik, product, generation, rung, date, URL or accession / news item, grade, status reported / confirmed / disputed, entered_at). UI: challenger list and form in the Moat section, DS16 shares beside. Live check: `uv run python scripts/run_moat.py challengers` (0 requests). Fixtures: Micron 2024-02-26 (A claim, rung 3 → warning, no CvD vote), Samsung Sep 2025 (B single → watch), the Samsung May 2024 dispute, CXMT rung 2, a rung 4 on two B → CvD "weakening", a verdict downgrade → "weakening".

## Live checks (owner runs, sends the log)
- Part 1: `uv run python scripts/run_moat.py quant`.
- Part 2: `uv run python scripts/run_moat.py challengers`.

## Open questions
- MU's class depends on the window (10 years vs full cycle): revisit with D-M04-83 cycle dates at tuning.
- Peers unconfirmed for AMZN, BA, GOOG, INFQ, META, MSFT, MSTR: their peer GM z reads "missing: peers not confirmed" until the owner's setup items are done.
