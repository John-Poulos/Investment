# M06 Moat — MVP brief
Updated 2026-10-21 (refreshed for sitting 3) · Source: docs/M06_DESIGN_PACK.md (research) · Status: for owner decision (sitting 3, with M03)

Research signals, not advice. Nothing here is decided until the owner answers (D7). Answers become D-M06-1 onward in a new `docs/M06_MOAT.md`; an M01 rule-1 amendment for the gate takes the next free D-M01 (D-M01-8, or -9 if Q03.8 takes -8).

## Since 2026-10-13 (what the refresh changed)
- **M04 8a is built** (PR #46): `market_share` (migration 0039, owner entries) is stored and `financials/cvd.py` has the Q2 row "Moat and challengers (M06)" reading "not applicable until M06" — Part 2's hook replaces that text. `cvd.turning_points` exists for a full-cycle window later.
- **The ROIC series helper is built** (M05 Part 1, D-M04-107: `financials/trends.py` `roic_series`), so Part 1 reuses it instead of writing its own loop. Its live log (2026-10-21) gives real engine ROIC figures, used in the worked example below.
- **Class rename (MVP_PLAN item 5, a default to strike):** M06's quant class "cyclical" is renamed **`through_cycle`**, because M08 owns the company-level "cyclical" flag (D-M08-3) and M04 owns the CvD states. The rest of this brief uses the new name.
- **Pre-assigned build numbers:** Part 1 migration `0043_m06_verdict`, D-STO-33, D-UI-40 (Moat section, verdict setup), DS21 (fluidity / TNIC); Part 2 `0044_m06_challenger`, D-STO-34, D-UI-42 (challenger list and form), next free D-M04 for the `cvd.py` hook. Wave W6, after sitting 3 and W5.

## D32: standard rows for every company, and rules whose evidence is tech-only
**Standard rows (default; strike if you disagree).** The Moat section shows the 10-year ROIC, gross margin and operating margin for every company, including those whose verdict is N_A (labelled, e.g. "asset vehicle: ROIC shown, not rated") and those whose gross margin is untagged ("missing: gross profit untagged", common for banks and services). The verdict and gate only add a reading; they never hide the numbers.

**Tech-only evidence (flagged as D9 failure modes):**
1. **R8 (HBM three-supplier oligopoly)** is one industry; "efficient scale" verdicts elsewhere get no help from it.
2. **The 4 seed challenger markets (Q06.7)** are all semiconductors. Retail, autos, pharma or industrial challengers only appear if the owner enters them.
3. **The `through_cycle` class** was built for MU's memory cycle; in other cyclical industries a window median above the hurdle may come from one boom. The last-3-years guard (rule 1) is the check.
4. **Book ROIC** misreads asset-light and R&D-heavy companies (every chip designer here) and is meaningless for banks and insurers (N_A by tag). The 8% hurdle and the 80% persistence share come from all-industry studies (fade ≈ 38%/yr, S-new-55), not from tech, so they are not watchlist-tuned.

## Purpose in one paragraph
Per equity: is there a moat, from which source, will it outlast the horizon, and is a named challenger catching up? Serves outline **Moat Check** 1–5 (no moat → no investment; vertical integration; process node/supply/IP; custom-ASIC switching costs; "can a competitor catch up in 3 years or less?") and the switching-cost/share part of **Identify the leaders** 2, and fills M04's CvD Q2 row "Moat (M06), challengers (R21)" (now "not applicable until M06"). Binding: **R1** (MY gate), **R8** (HBM three-supplier oligopoly), **A3** (duration ≥ timeframe), **R21** (sampling → small-scale → volume → qualified at a major customer), **R10** (AVGO–Google confirmed, AMD–Google C); D8, D13, D14, D16, D21/D28. **Departure from the pack** (written before the outline was in the repo): the pack used Morningstar's 10/20-year bands; the MVP uses the outline's 3-year catch-up test (Q06.3) and adds "vertical integration" as a source (Q06.4).

## Data already stored that the MVP uses
- **ROIC per fiscal year (S6.5):** `financials/trends.py` `roic_inputs()` / `roic()`. NOPAT = OI × (1 − tax ÷ pretax, bounded 0–35%), or OI when pretax ≤ 0. IC = equity + LT debt + current debt − cash − ST investments; average ≤ 0 → `not_meaningful`. Point-in-time via `facts_as_of`. M06 calls the same functions (operating income from `capex.fy_points`) over 10 years (the view shows 8); a ROIC year needs the prior year-end's invested capital, so 10 ROIC years need 11 balance sheets. Current debt is mapped (`debt_current` = `DebtCurrent`/`LongTermDebtCurrent`); no M04 code change.
- **Gross margin:** `trends._gross` (derived where untagged, labelled); peer GM z from `financials/peer_z.py` (D-M04-52) on `peer_group`/`peer_member`. Peers are still unconfirmed for AMZN, BA, GOOG, INFQ, META, MSFT, MSTR → their peer z reads "missing: peers not confirmed".
- **Routing:** `config/company_models.toml` tags via `financials/models.py` (MSTR `asset_treasury`, ETV `fund`, INFQ `spac_shell`).
- **Switching-cost evidence (shown, not scored):** `rpo`, `contract_liabilities` (`sec/xbrl_facts.py`); confirmed `supply_link` L1–L3 quotes (0020); `fact_dim` ≥ 10% customers (0035).
- **Challenger hints:** `news_item`/`news_company`/`news_theme` (0025, snippets, graded), `theme_phrase`, `config/aliases.toml` (SAMSUNG, SKHYNIX, AMD, AVGO, TSM). `news_company.cik` is NOT NULL, so non-SEC challengers (Samsung, SK hynix) never appear there: hints match their alias names in title/snippet at read time. **No CXMT alias yet** (one config line, 0 requests).
- **Market share — stored:** `market_share` (owner entries, M04 Part 8a, migration 0039; D-M04-68, DS16); M06 reads it and builds no second form; a company with no entry reads "missing: no share data".
- **Output:** `signal` (0029; D13 per D-M04-9/-74), `review_queue` (0001, 0013).
- **Missing:** leases and goodwill (unmapped → "excludes leases"); Item 1A year-over-year competition text (DS7 partly: M04 Part 3 stores the two prior annual reports as passages for core/promoted names; the comparison is not built); fluidity/TNIC (new gap — the pack's "DS17" collides with M04's ratings entry); user/installed-base KPIs (DS14, DS1); free WACC (none); any MY horizon (`position` has no horizon column).

## MVP signals (4)
`module_id = 'M06'`, keyed by `cik`, one row per timeframe. Missing = `method` "missing: <reason>", never zero.

| Signal | value / value_text | Meaning | Inputs | MY | PT | ST | Grade rule |
|---|---|---|---|---|---|---|---|
| `moat_quant` | share of window years with ROIC > hurdle (0–1); text persistent / through_cycle / weak / short_history / not_meaningful / not_applicable | Computed evidence leg (outline Moat 1; fade S-new-55) | S6.5 ROIC, GM median and dispersion (IQR ÷ 1.35), peer GM z; hurdle ±2 pp in `method` | ✓ | ✓ | info | A (XBRL); `source_ref` = newest 10-K "+N" |
| `moat_verdict` | value NULL; text WIDE / NARROW / NONE / UNRATED / N_A (states go in `value_text`, D-M04-9) | Owner-confirmed verdict (D8). Sources, catch-up band, reason and date in `method` | `moat_quant`, source labels, challenger rows, owner answer | ✓ | ✓ | info | Weakest deciding input: owner entry B, or A when it cites a verified stored filing passage (D14, D-M04-9) |
| `challenger_max_rung` | 0–4; text none / watch / warning | Highest R21 rung of a named challenger against this company, per market in `method` | Owner-entered challenger events | ✓ warn | ✓ warn | info | Grade of the deciding event; "warning" needs A, or two independent B |
| `moat_gate` | text met / not_met / unrated / not_applicable | R1 + A3 eligibility for MY entries | verdict, band low vs MY horizon, review age | ✓ gate | info | info | = verdict grade |

Readers (proposed): `moat_gate` → MY entry (M11 / M01 rule 1); `moat_verdict` → the one M06 confluence vote (M11 maps it), so the quant leg is not counted twice; challengers → CvD Q2 (rule 5). PT/ST: any band above 3 years exceeds the timeframe, so A3 holds there trivially (info).

**Rules (starting values, calibrated later):**
1. **Quant leg:** last 10 fiscal years with a computable ROIC (< 7 → `short_history`). persistent = ROIC > hurdle in ≥ 80% of years; through_cycle = below that but window median > hurdle **and** ≥ 1 of the last 3 years above it (R8 case; the guard keeps a decline like INTC's from reading as a cycle); else weak. Tags fund, financial (incl. untagged FF12 financials via `models.route`), reit, asset_treasury, spac_shell periods → `not_applicable`; `issuance_funded` is computed.
2. **Verdict:** engine proposes (persistent/through_cycle, no warning → NARROW candidate; weak → NONE; short_history → UNRATED; tag → N_A); owner enters verdict, source label(s), catch-up band (≤ 3 / 3–5 / 5–10 / > 10 years) and a reason. Band ≤ 3 = NONE (outline Moat 5), 3–10 = NARROW, > 10 = WIDE.
3. **Challengers:** rung per R21; rung 4 = qualified at a ≥ 10% customer of the incumbent (ASC 280, S77) or an owner-listed customer. Rung 1–2, or rung 4 on one B source → watch; rung 3–4 with A or two independent B → warning (never blocking, D16) and "re-check band" on the verdict. It reaches M01 rule 4 only through CvD (pack S5.2); M01's rule list is not changed.
4. **Gate:** met = NARROW/WIDE and band low ≥ MY horizon (A3); UNRATED → unrated (not met); NONE → not_met, shown; N_A → not_applicable, never "fail"; owner override logged (D12). The survival gate is not repeated here: M01 rule 1 already requires it (D-M01-6).
5. **CvD feed (D-M04-1 row, binding: intact = "unchanged; no challenger qualified", weakening = "challenger qualified at a major customer"):** weakening = rung 4 at a major customer with A or two independent B, or an owner downgrade of the verdict; intact = NARROW/WIDE, not downgraded, no such rung 4; else missing (leaves the denominator, D-M04-56). A rung-3 warning stays an M06 warning and does not vote in CvD (R21: trust is read at qualification).

## Worked example
Real unless marked illus. GM from the pack's companyconcept check (S-new-M06-17); 8% hurdle.

| Ticker | Real facts | `moat_quant` | Challengers | Proposal → gate (5-yr horizon) |
|---|---|---|---|---|
| MSFT | GM 64.0–69.8% FY16–26 (sd 2.0). FY26: OI 155.237, tax 32.185 ÷ pretax 165.934 = 19.4%, NOPAT ≈ 125.1; IC FY25 289.066, FY26 396.611 ($B) → ROIC ≈ 36.5% (pack arithmetic without current debt; the engine adds `debt_current` if tagged → slightly lower) | persistent, 10/10 (illus.); peer z missing (peers unconfirmed) | none entered | NARROW or WIDE (switching, network: hint) → met if band ≥ 5–10 |
| INTC | GM 61.7% (2018) → 32.7% (2024). OI 2021 19.456, 2022 2.334, 2023 0.093, 2024 −11.678, 2025 −2.214 ($B) | 2023–25 below 8%; if 2016–21 cleared it (illus., 6/10) the median does too → "through_cycle" without rule 1's last-3-years guard, weak with it | AMD x86 server unit share 28.8% Q4 2025 (B, S36/S224; M04's share row); AMD at rung 4 at a ≥ 10% customer (illus., owner enters) | NONE → not_met; with that rung 4 on A or two B the CvD Q2 moat row reads "weakening" — one more present row; whether AMBIGUOUS resolves depends on the others (D-M04-56, -63) |
| MU | GM −9.1% (FY23) to 80.7% (FY26; rev 133.188, GP 107.504 $B, acc. 0000723125-26-000023). HBM share 21% → 18% Q1 → Q2 2026 (B, S06, S-new-M06-15) | through_cycle, ≈ 6/10 above, median > 8%, FY25–26 above (illus.) | Samsung 12H "qualified at NVIDIA", Sep 2025 (B, one source, S-new-M06-14) → watch. CXMT rung 2 (B, S27) → watch. Micron's own rung 3 + H200 (A claim, 2024-02-26, S-new-M06-13) | Owner: NARROW (efficient scale, R8) or NONE |
| NVDA | GM 56.1–75.0% FY16–25, 71.1% FY26 | persistent (illus.) | AVGO–Google ASIC confirmed; AMD–Google grade C (R10) | NARROW/WIDE (vertical integration — the outline's CUDA lock-in, Moat 2 — and switching costs) |
| SPCX, INFQ (RIVN likely) | < 7 fiscal years | short_history | — | UNRATED → unrated |
| MSTR, ETV | asset_treasury, fund | not_applicable | — | N_A → not_applicable |

Fade check (S-new-55, ≈ 38%/yr): 10 pp of excess ROIC → 2.4 pp after 3 years. A high level alone is not persistence, which is why the leg counts years.

**Engine ROIC, latest fiscal year** (real: `trends.roic_series` as printed in the M05 Part 1 live log, logs/m05_demand_20261021-085637.txt; one year each, so the 10-year class above stays illustrative until Part 1 runs):

| Ticker (industry) | FY | ROIC | Against the 8% hurdle (±2 pp band) |
|---|---|---|---|
| MSFT | FY2026 | 35.9% | above (the pack's 36.5% was without current debt; the engine includes it) |
| NVDA | FY2026 | 149.8% | above; R&D-heavy, asset-light: label only (case 7) |
| MU | FY2026 | 106.7% | above at a cycle peak (case 6: never the latest year alone) |
| INTC | FY2025 | −1.1% | below — the last-3-years guard keeps INTC out of `through_cycle` |
| BA (aerospace, non-tech) | FY2025 | 13.5% | above in one year after 2019–24 losses → likely weak or `through_cycle`; the D32 test case |
| TSLA (autos) | FY2025 | 8.1% | inside the ±2 pp band: the class can flip on the hurdle choice (Q06.1) |
| GFS (foundry) | FY2025 | 8.3% | inside the band |
| RIVN (autos) | FY2025 | −114.6% | below; short history → UNRATED |

## Cases the rules must handle
1. History (years with a computable ROIC): ≥ 10 full window; 7–9 computed, "short window"; < 7 → short_history → UNRATED.
2. Own fiscal years; peers on M04 offsets (D-M04-5).
3. Tag gap or switch (NVDA FY2019 `Revenues`) → `facts_as_of` walk, else year missing, never interpolated; share on present years.
4. Average invested capital ≤ 0 (buybacks) → year `not_meaningful`, left out; most years → leg `not_meaningful`.
5. Pretax ≤ 0 → NOPAT = OI, losses kept negative (INTC); tax rate bounded 0–35%, named.
6. Peak margins mislead (MU FY26 80.7%) → years counted plus median, never the latest year alone.
7. Capital distortions: cash subtracted, equity stakes not (MSFT); leases unmapped → "excludes leases"; acquisition year → M04 flag beside it; R&D-heavy (NVDA, INTC, MRVL) → label only.
8. Moat in one segment (AWS in AMZN) → "consolidated only".
9. Fund, financial, asset vehicle, SPAC-shell period → N_A, never "fail"; stage does not route M06.
10. Several sources (MSFT) → several labels on one verdict.
11. Owner-cited passage → quote verified mechanically (D21); unverified → rejected, stored.
12. Non-SEC challenger (Samsung, SK hynix, CXMT) → alias key, CIK NULL.
13. Company both incumbent and challenger (MU; MRVL/AVGO custom ASICs: a switching-cost moat with their customers, outline Moat 4, and a challenger to NVDA) → event read per role.
14. Disputed press report (Samsung 8H, May 2024) → status disputed, not counted.
15. Rung skipping → earlier rungs missing; qualified with small orders → rung 4, share tracked apart (DS16); generation per event (HBM3E vs HBM4).
16. Unnamed "major customer" (S78) → B at best unless the ≥ 10% or owner-list rule holds.
17. Name collisions ("Samsung" phones, "HBM" acronyms) → hints only, never auto-entered.
18. Verdict older than the latest 10-K → "stale since <date>" shown; a changed quant class or a new warning re-opens it.
19. Band low < MY horizon → not_met (A3); override → reason logged, "override" shown.
20. Anchoring on the proposal (D9) → card shows evidence for and against.
21. Grade mixing (B shares beside filing facts) → weakest deciding input.
22. Backtests → `facts_as_of(as_of)`; verdicts and events carry entry dates, nothing back-dated.

## Deferred to the tuning phase
- R1 S1.1 `m06_metrics` table, turnover, margin × turnover label (S1.3) — display extras; MVP computes on the fly.
- R1 Q1.2 R&D-capitalised and goodwill-free ROIC — recipe unverified (S-new-M06-11).
- R1 Q1.3 full-cycle window — needs D-M04-83 cycle dates (8a).
- R2 S2.1–S2.3 `m06_source`, pattern proposals, Gemini hints — owner labels on the verdict suffice (D28 later).
- R2 S2.4/Q2.2 share form — settled by D-M04-68 (DS16).
- R2 Q2.3 separate industry and firm ratings — the MVP rates the firm; R8's industry state shows as the "efficient scale" label with DS16 share rows beside it.
- IP/patent evidence (outline Moat 3) — PatentsView unverified; the MVP uses the owner's "intangibles" label with a verified quote. Product design and roadmaps (outline Leaders 2) → M03.
- R2 S2.5 competition text, fluidity (S-new-M06-6, -7) — DS7; gvkey map, data end 2023.
- R2 S2.6 KPI extractor (META, AAPL) — DS14/DS1.
- R3 `moat_trend`, S3.4 cadence, fade fits — challenger warning and M04 GM rows cover the MVP.
- R3 Q3.2 per-position horizon — M11 owns positions.
- R4 S4.3 rung phrase finder, S4.6 durations, Q4.1 digest — owner entry is enough for 4 markets.
- R5 S5.4 blind first look, PT/ST gate variants (S5.3) — after use.
- SOURCES fixes (S14 URL, S06, S27 date) and S-new renumbering — with the module doc.

## Questions for the owner
**Q06.1 ROIC hurdle**
- a) *Recommended.* Fixed 8% after tax, ±2 pp shown in `method`. Transparent; no free WACC exists (S14 = S-new-M06-1).
- b) 10% fixed.
- c) Peer median ROIC (n < 5 for most names, D-M04-52).

**Q06.2 Quant-leg rule**
- a) *Recommended.* 10 fiscal years (≥ 7 needed); persistent ≥ 80% of years above the hurdle; through_cycle = window median above it with ≥ 1 of the last 3 years above. Fade ≈ 38%/yr makes years, not level, the evidence (M04 pack S-new-55); the median keeps R8 names like MU from failing on troughs, and the recent-years guard keeps INTC's decline out of "cyclical".
- b) Same, without the recent-years guard (INTC may read "through_cycle").
- c) Persistence share only, no through_cycle class.
- d) As (a) on 5 fiscal years.

**Q06.3 Duration scale (A3)**
- a) *Recommended.* Outline test, owner-entered catch-up band ≤ 3 / 3–5 / 5–10 / > 10 years; ≤ 3 = NONE, 3–10 = NARROW, > 10 = WIDE. Follows outline Moat 5 and gives A3 a number.
- b) Morningstar bands: narrow ≥ 10, wide ≥ 20 (S14).
- c) Both shown; the gate uses (a).

**Q06.4 Source labels**
- a) *Recommended.* Morningstar's five (intangibles, switching costs, network, cost advantage, efficient scale) plus "vertical integration". The outline names it (Moat 2); the five cover the rest (S-new-M06-1, p. 2).
- b) Morningstar's five only.
- c) The outline's three groups only (vertical integration; process/supply/IP; custom-ASIC switching).

**Q06.5 Override and UNRATED names under the MY gate** (R1 makes the gate itself binding; only its exceptions are open)
- a) *Recommended.* Logged override allowed; UNRATED = not met, but the owner may enter a qualitative verdict marked grade B. Allows documented exceptions and keeps young names (SPCX, RIVN) reachable without a faked record (pack 5.1a/5.2a).
- b) Logged override allowed; UNRATED stays not met until 7 years of ROIC exist (pack 5.2b).
- c) No override.

**Q06.6 MY horizon for A3**
- a) *Recommended.* One global default of 5 years in config; per-position horizons arrive with M11. M01 leaves MY open and the `position` table has no horizon.
- b) 10 years.
- c) Per-position now (needs an entry screen M11 owns).

**Q06.7 Challengers in the MVP (R21)**
- a) *Recommended.* Owner-entered events for 4 seed markets: HBM (MU vs SK hynix, Samsung, CXMT), x86 server (INTC vs AMD), foundry (INTC/GFS vs TSMC), AI accelerators (NVDA vs AVGO/MRVL ASICs, R10). Stored news headlines are listed as hints, and events can be entered in any other market. Evidence is mostly B and reversible (S-new-M06-14); customers often go unnamed (S78). D32 flag: all four seed markets are semiconductors.
- b) HBM only.
- c) Owner-entered events in any market, no seed list and no news hints (R21 is binding, so challenger tracking itself is not optional).

**Q06.8 Verdict review cadence**
- a) *Recommended.* One setup batch now (15 items: 17 covered minus ETV and MSTR). After that, re-open only when a new 10-K changes the quant class or a challenger warning is entered; other verdicts show "stale since <date>". Data move yearly and challengers on events (pack Round 5); it keeps the queue small.
- b) Re-review every company at each 10-K plus events (the pack's 5.4a).
- c) Quarterly.

## Build parts
**Part 1 — Quant leg, verdict, gate.** Code: `src/engine/moat/` `quant.py` (reuses `trends.roic_series` (D-M04-107), `_gross`, `peer_z`), `verdict.py`, `gate.py`, `step.py` (local refresh pass after M04, 0 requests); `scripts/run_moat.py`; `config/moat.toml` (hurdle, horizon). Table (migration 0043): `m06_verdict` (cik, verdict, sources, band, reason, passage ref, grade, override, decided_at, as_of). Review kind `m06_verdict` (setup batch, re-open per Q06.8; outside M04's cap). UI: "Moat" section on the Financials tab (10-year ROIC/GM, class, verdict card with RPO, contract liabilities, confirmed supply links); verdict form on a setup page beside `/m04/setup`; mock-up first on MSFT/INTC/MU (D-UI-4). Live check: `uv run python scripts/run_moat.py quant` — 0 SEC/API requests, < 1 min; one row per company, 15 setup items. Fixtures: MSFT FY25–26 inputs (36.5% on the pack's terms; the expected value is recomputed with `debt_current` if tagged), INTC 2021–25 OI (10-year window → weak only through the last-3-years guard), MU FY23/FY26 GM, a 6-year company, MSTR/ETV, an IC ≤ 0 year. Depends on M04 1b, 1c, 2 (built); not on 4b-lite or 8a.

**Part 2 — Challengers and the CvD feed.** Code: `moat/challengers.py` (events, rung logic, news hints by market phrase + alias); hook in M04 8a `cvd.py` replacing "not applicable until M06" (rule 5); M01 reads it through `cvd_state`, no M01 change. One `config/aliases.toml` entry for CXMT (owner-edited file). Table (migration 0044): `m06_challenger` (market, incumbent cik, challenger key/cik, product, generation, rung, date, URL or accession/news item, grade, status reported/confirmed/disputed, entered_at). Review kinds: none (owner entry is the confirmation). UI: challenger list and form in the Moat section, DS16 shares beside it. Live check: `uv run python scripts/run_moat.py challengers` — 0 requests, < 1 min (hint counts per market; INTC CvD before/after). Fixtures: Micron 2024-02-26 (A claim, rung 3 → warning, no CvD vote), Samsung Sep 2025 (B single → watch), Samsung May 2024 dispute, CXMT rung 2, a rung 4 on two B → CvD "weakening", a verdict downgrade → "weakening". Depends on Part 1, M04 8a (`cvd.py`, `market_share`), M02 news (built).

## Open risks
- Verdicts rest on owner judgement (B); the quant leg is the only A evidence and cannot see young or segment moats.
- Book ROIC biases (leases, R&D, goodwill, buybacks); 8% is a convention, not a WACC.
- Challenger evidence is mostly press (B), reversible and entered by hand; hints are snippet-only and collision-prone.
- MU's class depends on the window (10 years vs full cycle) — revisit with D-M04-83 in 8a.
- One global horizon until M11; Part 2's `cvd.py` hook edits M04's built 8a code (next free D-M04).

## Check notes (2026-10-13)
Checked against the pack, the outline, DESIGN revisions, M04/M01/M02 docs and the code (`trends.py`, `xbrl_facts.py`, `peer_z.py`, `models.py`, migrations 0001–0037, `config/*.toml`).
1. **Binding, D-M04-1 row:** the CvD feed voted "weakening" at rung 3; the row says "challenger qualified at a major customer" (rung 4) and "unchanged" for intact (R21: trust at qualification). Rule 5: rung 4 (A or two B) or a verdict downgrade → weakening; rung 3 stays an M06 warning. Fixtures updated.
2. **Binding, R1/R21:** Q06.5(b) "no gate" and Q06.7(c) "no challengers" contradicted approved revisions; Q06.5 now asks only override and UNRATED handling, Q06.7(c) is a no-seed-list variant.
3. **Binding, D-M04-9:** `moat_verdict` put 2/1/0 in `value` beside its state; states go in `value_text`, `value` NULL. Fixed.
4. **M01 scope:** challenger warnings were made an M01 rule-4 reason (an M01 change); now via `cvd_state` only (pack S5.2). Gate notes the survival gate is already in M01 rule 1 (D-M01-6).
5. **Rule flaw:** by the brief's own rule INTC (if 2016–21 cleared 8%) reads "cyclical", like MU, not "weak". Added a last-3-years guard to rule 1 and Q06.2(a); unguarded rule is (b); 5-year window kept as (d).
6. **Data reality:** `market_share` is not stored (M04 8a, unbuilt, migration 0039). DS7 is partly closed (two prior annual reports stored by M04 Part 3). `news_company.cik` is NOT NULL → non-SEC challengers matched by alias text only; no CXMT alias (added to Part 2). 7 names lack confirmed peers → peer GM z missing. `debt_current` is mapped, so "MSFT current debt absent" was unverified; 36.5% now labelled the pack's arithmetic. Tags: added `reit`, FF12 financials; `issuance_funded` computed. All other named tables, columns, functions, routes and configs verified.
7. **Outline fit:** CUDA is the outline's vertical-integration example (Moat 2), relabelled; MRVL/AVGO custom ASICs (Moat 4) added to case 13; IP/patents (Moat 3), roadmaps (Leaders 2 → M03) and firm-vs-industry rating (R8, pack Q2.3) added to Deferred.
8. **Sources:** S-new-M06-13/-14/-15 cited on the MU row; Q06.8(a) was attributed to pack 5.4a, which is option (b); fixed. Other IDs exist.
9. **MVP discipline / overlap:** 4 signals, 8 questions, 2 parts, 0-request live checks unchanged; readers line keeps one M06 confluence vote; no M04/M02 signal duplicated (AMD share fixture dropped: M04's share row owns it).
