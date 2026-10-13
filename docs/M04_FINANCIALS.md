# M04 — Financials & red flags

Status: design complete 2026-10-12, D-M04-1…83; build parts in M04_BUILD_LOG.md · Updated: 2026-10-12 · Outline headings: Analyze the financials; Financial red flags · Depends on: M00 (SEC data), M02 (capex recipes and guided-vs-actual, allocation block, guidance freshness, DSO, supply links), M06, M11 (R19 ledger) · Sources: S02–S04, S13, S20, S25, S32–S37, S39–S41, S43–S45, S47, S50, S56, S81, S88, S97, S100, S103, S105, S109, S110, S112, S121, S123–S225 (M04 review; provisional-ID map at the end of M04_DESIGN_PACK.md)

Every rule cites its D-M04-n; suggestion IDs (S1.x–S6.x, SB.x) point to the round briefs in docs/m04_review/. Thresholds marked † are starting values, calibrated at Part 8b (D-M04-51) or, for red flags, at the High review after 8b (D-M04-73). Missing data stays missing (`method` = "missing: <reason>"), never zero (D-M04-9). Outputs are research signals; the owner decides (D8, D16).

## Purpose
Judge financial health and earnings quality, flag the outline's red flags by life-cycle stage (R2), and classify a slowdown as cycle or decline (CvD) for M01's entry and exit rules (D27).

## Inputs
| Data | Source | Grade | Refresh |
|---|---|---|---|
| Point-in-time facts: `facts_as_of()` (periodic forms only, tag priority after time, de-SPAC boundary); every value carries tag and accession (S1.1, S1.4) | `fact` (companyfacts) | A | Logon refresh, per new filing (D-M04-70) |
| Share series `shares_period_end`, `shares_cover`, `shares_basic_wavg`, `shares_diluted_wavg`, `sbc`; multi-class cover from R1 pages; implied float (D-M04-2) | `fact`; R1 pages | A | Per new filing; multi-class R1 ~1 per filing |
| Capex: display = M02's company-definition recipe (clause-derived, toml override, approximate label and shown-actual rule, D-M02-29/-32/-34) with the standard-tag value beside it and the D-M04-3 marker worded "broader tag: <what it adds>" (e.g. "includes intangibles"), so it cannot be confused with M02's "≈, gap X%"; longest consistent tag for own history; PP&E tag only for peers (D-M04-3); `capex_split` ladder (D-M04-6) | `moneyflow/actuals.py` (`config/capex_definitions.toml` overrides); `fact`; NVDA instances | A | Per new filing |
| Peers: 4-digit SIC proposals from a ranked shortlist, owner-confirmed `peer_group`; non-SEC peers "missing" (D-M04-4); periods TTM ±45 d, quarters/instants ±40 d† (D-M04-5); peer facts trimmed to M04 tags (D-M04-75) | submissions, browse-by-SIC (S162), companyfacts; SIC vs other schemes (S163) | A | Peer companyfacts on a new peer filing |
| Life-cycle stage, owner-confirmed (D-M04-7, -12) | Cash-flow totals in `fact`; owner | A (owner confirmation) | Per new 10-K |
| Model tags (D-M04-8) | `config/company_models.toml`, hand-edited | Owner | On edit |
| Guidance record, `guidance_hit_rate` (D-M04-10) | Guidance ledger (`guidance/`), first-filed facts; capex actuals from M02's `moneyflow/guided.py` (recipe in force at the guide date, D-M02-29); M02 freshness states (D-M02-30) | A; B if from a transcript | Per earnings release |
| 8-K items 1.01–1.03, 2.01, 2.04, 3.01–3.03, 4.01, 4.02, 5.06 (D-M04-15, -28, -37) | `event` | A | Logon refresh |
| Filing text: going concern, covenants, restatement wording, causes, estimates, credit lines, overhang, ratings (D-M04-15, -19, -34, -41) | corpus (FTS5), EFTS one-off history | A (verified quote) | Finders run on stored text |
| Dimensional facts: segments, customers, missing 10-Q lines (D-M04-42) | Filing instances → `fact_dim` | A | One instance per new 10-K/10-Q |
| Unit KPIs, credits (D-M04-42) | `unit_metric`: Tesla DS2, EX-99.2, 10-K sentences | A | Per release |
| 424B fee exhibits, shelves (D-M04-24) | Filing index, fee exhibit | A | Per new 424B |
| Issuance bands (D-M04-23) | CY frames (float ≥ $700M, SIC 6770 out) | A | Once a year |
| Daily closes; delisted symbols only on name and date match (D-M04-72, S6.15) | Tiingo | Market data (see Open questions) | Logon price step: core and promoted daily, tracked in a 3-day rotation (D-M02-12, -18); rows name the close date used |
| Owner entries: market share (D-M04-68), undrawn credit, stickiness class (D-M04-43), peer and stage confirmations | Setup page, review items | B without a filing source; A with one (D-M04-9) | On entry |

## Company profile

### Life-cycle stage (R2)
- **Computed:** Dickinson signs of (CFO, core investing, financing); core investing = capex + acquisitions − asset and business sale proceeds. A stage holds when 2 of the last 3 fiscal years agree (D-M04-7).
- **Review (`m04_stage`)** when no stage holds 2 of 3, the held stage is shake-out, the stage conflicts with 3-year revenue CAGR (introduction/growth with CAGR < 0; mature/decline with CAGR > 20%†), or fewer than 3 fiscal years exist (D-M04-7).
- **Confirmation:** the owner confirms each company's first stage once (setup batch, 15), then computed changes and ambiguous cases, about 4–5 a year (D-M04-12). Owner override.
- **Until confirmed:** the last confirmed stage routes. With none, the young and the mature flag sets are both computed, labelled "stage unconfirmed" and not counted in D13 (D-M04-7).
- Stage routes flags only. R12, inventory-vs-sales and the survival gate run at every stage (D-M04-7).
- **Built (Part 1c):** `financials/stage.py`; capex = the own-history total capex (D-M04-3); acquisitions and sale proceeds without a fact count as none and are named; a value > 0 reads "+". The refresh's local pass recomputes every core and promoted company (tracked names: no items, D-M04-80); the first run opens one setup `m04_stage` item per company (15, outside the cap); later, a new fiscal year whose computed stage differs from the owner's, or is ambiguous, opens a capped item (group 2). Owner override from the setup page, recorded as a resolved item.

### Peer shortlist (D-M04-4; built Part 1c)
- Listed = EDGAR's browse-by-SIC under the company's 4-digit SIC (one browse per SIC — the form parameter does not filter the list — at most 10 pages, partial marked when the last page read was full); active = a 10-K, 20-F or 40-F (incl. amendments, 10-KT) in the last 12 months from the stored form indexes; ranked by |ln(peer revenue ÷ company revenue)| on calendar-year revenue frames (3 tags), "revenue suspect" names after them (CY ÷ CY−1 above 10× or below 0.1×, or more than 10× off the company's own stored annual revenue; marked, never dropped), names without a frame value last; top 10† per company.
- One setup `m04_peer` item per company from the shortlist only; the owner strikes names, adds product-market peers in any SIC by ticker or CIK (WDC, QCOM for MU) and non-SEC peers by name ("missing: not an SEC filer": SK hynix, Samsung), and confirms; the set goes to `peer_group` / `peer_member` ("M04 peers <cik>"). A tagged company (MSTR) gets no SIC shortlist, only owner-added peers; `fund` and `financial` get no item. `run_financials.py profile` is the only browse (owner-run).

### Model tags
Six fixed tags; one-line reason and source each; unknown tag rejected at load; the app never edits the file. A tag overrides SIC and applies before stage. Untagged financials (FF12 group 11) read "not applicable"; the engine may propose `reit` for SIC 6798 (D-M04-8).

| Tag | Earnings quality | Dilution | Survival gate | Health scores, CvD |
|---|---|---|---|---|
| (none) | normal | normal (D-M04-25) | full | normal |
| `issuance_funded` | normal | review while gate passes outside the warn band; else `financing_pressure` warns (D-M04-13) | full (D-M04-13) | normal; equity point per D-M04-65 |
| `asset_treasury` | NI, accruals, M-score "not meaningful" | review (D-M04-25) | liquidity-only | Z "not meaningful" |
| `reit` | excluded | review | liquidity-only | excluded |
| `fund`, `financial` | excluded | excluded | not applicable (D-M04-35) | excluded |
| `spac_shell` | excluded | not meaningful | trust only; text excluded (D-M04-34) | excluded |

Initial entries: MSTR `asset_treasury`, ETV `fund`, INFQ `spac_shell` for periods ending before 2026-02-13, keyed on period end (D-M04-8, probe S12). Excluded rows are written as "missing: not applicable (<tag>)" (S5.1).

### Filing status
- `filing_status` = current / stale / overdue (S1.6, S6.13).
- **Due date** = period end + the deadline for the filer's status: 10-K 60/75/90 days, 10-Q 40/40/45, 20-F four months; an NT filing adds 15 (annual) or 5 (quarterly) days. Live status from submissions `category`. In backtests, status is derived from stored public float under Rule 12b-2, with exit thresholds applied only to an issuer already in the category (status carried year to year; Invitae is the regression case). The longest deadline is used only when float is missing (S1.6, D-M04-36).
- **Overdue** → survival gate incomplete and an exit warning (D-M04-61).
- **Stale** → once a period has ended unfiled, the carried CvD state is marked stale. The first tranche may use it; later tranches wait for the filing (D-M04-61).
- **Input age:** older facts are labelled "as of <date>". Foreign annual filers use annual burn for up to 16 months, then the gate is incomplete (D-M04-36).
- **Re-evaluated on every logon run:** overdue and stale come from the calendar (a due date passes with no filing), not from a new filing, so `filing_status`, the stale mark and the gate state are recomputed for every covered company on each run (local, 0 SEC requests; D-M04-61, D-M02-12; M04_BUILD_LOG.md "Logon-refresh constraints").

## Cycle vs. Decline (CvD) profile
Approved structure of D-M04-1, amended. A changed cell carries its D-M04-n. Units: pp = percentage points.

### Activation
CvD runs when the latest filed quarter shows any of: TTM revenue down year over year; TTM gross margin down ≥ 3 pp†; TTM operating income down ≥ 25%† (D-M04-55); the latest quarter's revenue ≥ 10%† below a year earlier (D-M04-67). It switches off after 2 straight quarters with none of these (S6.9). Otherwise `cvd_state` = NO_SLOWDOWN (D-M04-55).

### Peer statistics
- Robust z = (company − peer median) ÷ scale. Scale: IQR ÷ 1.35 for ≥ 10 peers; MAD × 1.4826 × b_n for 5–9 peers; fewer than 5 → fixed-gap fallback, z information only. Drop any peer with |z| > 3 once and recompute (D-M04-52). Method, n and b_n stored; the gap in pp always shown (S6.2).
- A peer period counts only inside the offset tolerance (D-M04-5) and from its filing date; otherwise "awaiting peer filing" or "no comparable period" (missing), which counts toward the < 5 fallback (S6.1). 2-quarter persistence kept.
- **Built (Part 2):** `financials/stats.py` (b_n = 1.206, 1.200, 1.140, 1.129, 1.107 for n = 5…9 from revss; IQR type 7 at ≥ 10; drop once only with ≥ 5 peers; below 5 the information z uses MAD × 1.4826 × b_n with b_2…b_4 and the spread of four methods is shown), `financials/peers.py` offsets (closest end within ±45 d for 12-month flows, ±40 d for instants; "awaiting peer filing" when the peer's latest period ends before the company's and its next quarter would land inside), 53-week flag (12-month period ≥ 370 days), acquisition-year flag (cash for businesses or a goodwill rise ≥ 10%† of the 12-month revenue; AMD FY2022), `financials/peer_z.py` (every core trend row computed the same way for company and peers; 12-month rows on the latest TTM or fiscal year, CAGR and FCF growth on the latest fiscal year, ROIC at fiscal year ends ±40 d; capex rows on the PP&E tag only, NVDA and AMZN excluded every year), `financials/peer_facts.py` (trimmed companyfacts per confirmed SEC peer). No peer set → "peers not confirmed on the M04 setup page"; an empty confirmed set → "no peers confirmed" (not the fallback). The owner can reopen a confirmed set from the setup page ("Edit peers"); removed peers keep their facts but leave every comparison.

### Q1 — Is the slump shared?
| Indicator | Shared (cycle) | Company-specific | Neutral / missing | Source |
|---|---|---|---|---|
| Revenue growth vs peers (TTM YoY), robust z | Peer median < 0, any z; z ≤ −1 flagged `deeper_than_peers` (D-M04-55) | z ≤ −1.5† for 2 straight quarters while peer median ≥ 0 | Peers growing and z > −1.5 → neutral (D-M04-55) | `fact` + confirmed peers (D-M04-4) |
| Fallback when < 5 peers (low confidence) | Peers falling; ≥ 10 pp below → also `deeper_than_peers` (D-M04-55) | Gap ≥ 10 pp† below while peers grow | Peers growing, gap within 10 pp → neutral (D-M04-55) | Same |
| Industry pricing / volume | Falling industry-wide | Stable or rising | Missing until DS13 exists (S6.11) | Industry series; trade press (B) |
| Inventory days (average inventory, write-downs added back; R1 brief, probe L9) | Rising across peers | Rising only here | — | XBRL |
| Supply response | Peers cutting output or capex together, read with the company's own absolute capex cut (S6.4) | Peers expanding | — | Filings, calls (R19) |
| Cycle history | Prior downturns of similar depth recovered | First deep decline | Before XBRL → "insufficient history", never "first deep decline" | 10+ years of filings |

### Q2 — Is the franchise intact?
| Indicator | Intact | Weakening | Neutral / missing | Source |
|---|---|---|---|---|
| Market share (D-M04-68) | Not down ≥ 1 pp | Down ≥ 1 pp† over 4 quarters in a flat or growing market | "missing: no share data" | Owner-entered third-party share (B) or share of a stated industry total (A) |
| Gross-margin gap to peer median | Change ≥ −3 pp over 4 quarters | Change < −5 pp | −5 to −3 pp → neutral; votes only with ≥ 3† comparable peers (S6.10); no gross-profit line → "not like-for-like" (S5.12) | XBRL |
| Trough vs prior trough (GM and ROIC) | Neither GM nor ROIC shows lower lows and lower highs (D-M04-54) | Both show lower lows and lower highs over 2 cycles | GM and ROIC disagree → neutral; < 2 prior troughs → "insufficient history". Turning points need a 5 pp† swing; write-down quarters adjusted (D-M04-54) | XBRL; ROIC per S6.5 |
| Capex and R&D (D-M04-54) | Total capex ÷ revenue and R&D dollars both held near own 3-year average and peers | Either cut > 20%† while peers hold | Capex ÷ revenue > 1.5×† own 3-year average while revenue falls → neutral, pointer to M05 (D-M04-64); tag switch in window → not scored (D-M04-3) | XBRL; peers on the PP&E tag only |
| Moat (M06), challengers (R21) | Unchanged; no challenger qualified | Challenger qualified at a major customer | Not applicable until M06 (S6.11) | M06 |
| Customer base, by owner-confirmed stickiness class (D-M04-43) | Within own historical range | Design-in: owner-confirmed loss (agreement ended, share below own 3-year minimum while revenue flat or down, replacement supplier named). Contracted: RPO below its 3-year minimum for 2† quarters (D-M04-49) | RPO ÷ revenue break alone → review only (D-M04-49); transactional weight 0; no data → missing, never intact | Instance axes, else sentences; customer-named 8-Ks only (D-M04-43); RPO |
| Guidance record (D-M04-10) | Hit rate steady | 2† misses in the last 4 guided quarters, or a quiet removal (only in M02's freshness state "not restated", D-M02-30) | Point and "approximately" guides unscored; cost metrics miss above the high end, tax rate and other income unscored, capex only on an exact recipe (D-M04-84); only core-family removals count (D-M04-85); release-silent → "missing (DS1)"; call not stored yet or results not read yet → missing with that reason | `guidance_hit_rate` |
| Health score (D-M04-53, -59, -65) | F-quality ≥ 4 of 5 | F-quality ≤ 2 | 3 → neutral; Piotroski F and Mohanram G shown, not voted | XBRL |
| R12 cause (new vote, D-M04-44) | — | Owner-confirmed price, mix or competition cause | Present only when it fires (D-M04-56) | R12 episode |

- **F-quality** (0–5): accruals, leverage, liquidity, equity, CFO > 0 (D-M04-53, -59). The equity point uses the Round 3 measure routed by tag then stage; it is lost only on extreme or serial issuance, and for `issuance_funded` only when `financing_pressure` warns; unconfirmed stage → missing (D-M04-65).
- **Customer weight:** design-in vote = min(1, revenue at stake ÷ 0.25†); contracted 1; transactional 0; missing excluded (D-M04-50).
- **Open 4.02:** rows reading the affected periods are marked "inputs under non-reliance" and warn; adds are not blocked (D-M04-21).

### Classification
Each row returns a side, neutral (present, no side), or missing with its reason; missing rows leave the denominator. A question needs ≥ 2 present rows and one side holding ≥ 2/3† of present weight; otherwise AMBIGUOUS → `m04_cvd` review, and the owner's answer becomes the state (D-M04-56, D-M04-63). The grid's "review" for STUMBLE and CYCLE_PLUS_DAMAGE (D-M04-1) is the same `m04_cvd` item, and the owner's answer becomes the state in the same way.

| | Franchise intact | Franchise weakening |
|---|---|---|
| Shared slump | CYCLICAL_TROUGH → adds allowed on M01 trigger | CYCLE_PLUS_DAMAGE → exit warning (M01 rule 4); `m04_cvd` review |
| Company-specific | STUMBLE → `m04_cvd` review | STRUCTURAL_DECLINE → no adds; exit warning |
| Not active (D-M04-55) | NO_SLOWDOWN | |
| No 2/3 majority or < 2 rows (D-M04-56) | AMBIGUOUS → review | |

- `cvd_confidence` = the lower of the two questions' winning shares; `cvd_coverage` (present ÷ applicable rows, per question) is shown beside it (D-M04-56).
- Regression cases: MU 2022–23 → CYCLICAL_TROUGH; INTC 2022–25 → AMBIGUOUS until the share and moat rows exist, owner's answer expected (D-M04-63); Invitae 2022–23 → survival gate fails.

### Normalized earnings power (NEP)
- Cycle-average operating margin (ratio of sums) × current revenue — the gauge base — and × cycle-average revenue, both shown (D-M04-54).
- Reported and ex-items bases both shown; an item is excluded only if nothing similar occurred in the prior 10 years; repeats feed `special_items` (D-M04-66).
- Outside CYCLICAL_TROUGH and AMBIGUOUS it is labelled "not used: <state>" (S6.6).

### Overreaction gauge (informs, never overrides)
- Gap = 4-quarter price change − change in NEP on current revenue, same 4 quarters (closes at the latest filed quarter-end and 4 quarters earlier); flagged at ≤ −25 pp† (D-M04-57). The cycle-average base is shown beside it; a live line uses the latest close, labelled "after period end" (S6.12).
- Not needed for rule-7 strength (D-M04-62). No matching price symbol → "missing: no prices" (D-M04-72).
- CYCLICAL_TROUGH with a large gap is the owner's target setup.

## Survival gate (overrides the grid)
Liquidity and legal facts only; runs at every stage; scope by model tag (D-M04-8, -13, -31). Altman Z, Z'' and Ohlson O are out of the gate (`distress_score`, Red flags).

- **Liquidity** = cash + short-term investments (restricted cash excluded) + undrawn committed credit that is confirmed and matures beyond the horizon (D-M04-32, S4.2).
- **Burn** = −(OCF − total capex), the worse of TTM ÷ 4 and the last two quarters (D-M04-32).
- **States** (`value_text`): pass, warn (counts as pass for M01, D-M04-31), fail, incomplete (required input missing, overdue, or withheld for inconsistent inputs), not applicable (D-M04-35, S4.1).

| Test | Fail | Warn | Review |
|---|---|---|---|
| Runway, cash burner (OCF < 0 on TTM or last two quarters; `issuance_funded` included) | < 6 quarters | < 8† | — |
| Runway, capex-funded (OCF > 0, FCF < 0) | never | < 8† | < 6†: rule-3 adds allowed, rule-7 strength blocked while open (D-M04-38) |
| Maturity wall (D-M04-33) | 12-month debt > liquidity, every gated name; commercial paper never added twice | 12-month debt + 4 × burn > liquidity | 24-month wall shown |
| Going-concern and covenant text (D-M04-34) | Auditor going-concern paragraph; management "substantial doubt exists"; unwaived covenant breach; forbearance; covenant-driven reclassification of debt | Alleviated doubt; audit-matter-only mention; waived or reset covenant → warn + review | Hypothetical wording, only when runway < 8 quarters |
| 8-K (D-M04-37) | 1.03 (never clears by itself); 2.04 until a later clean periodic filing and owner resolution; 3.01 delisting or missed cure | 3.01 cure-period deficiency → warn + review | 3.01 listing transfer = information (S1.11) |
| Filing status (D-M04-36, -61) | — | — | Overdue → incomplete + exit warning; foreign annual filer > 16 months → incomplete |

- Self-funding (FCF ≥ 0 on both measures) passes the runway test. "Runway without growth capex" (from `capex_split`) and the OCF-only runway are information (D-M04-6, S4.2).
- Text findings use verified quotes; `spac_shell` periods are excluded, keyed on period end; a one-off EFTS pass sets the history baseline (D-M04-34).
- **Scope:** liquidity-only gate for `asset_treasury` and `reit`; trust only for `spac_shell`; not applicable for `fund`, `financial` and untagged FF12 group 11, read as not-pass by M01 until a sector gate exists (D-M04-8, -35).
- **Open 4.02:** the gate is marked "inputs under non-reliance" and warns; it is not set to incomplete (D-M04-21).
- Regression: Invitae fails at the FY2021 10-K (715 days before its 8-K 1.03); Boeing FY2019 runway 5.9 and Q2 2024 5.5 → fail, wall passes; Intel FY2024 capex-funded → warn + review (D-M04-32, probe).
- **Built (Part 4a; `financials/gate.py`, `distress.py`, `debt.py`, `gate_step.py`, `gate_view.py`):**
  - Burn bases: the last two quarters (contiguous, derived from year-to-date facts as filed) and TTM ÷ 4 at the same end; fewer than four quarters → last two only ("short history"); one quarter → incomplete; a foreign annual filer whose latest period is a fiscal year uses fiscal year ÷ 4 until 16 months after it, then incomplete (D-M04-36). Total capex on the Part 1b own-history definition, the other definition's tags as fallback; a broader tag is named. Capex untagged → OCF-only runway, labelled, plus an `m04_gate_input` item.
  - Tiers per basis sums: OCF < 0 on either basis → cash burner; else FCF < 0 on either → capex-funded; else self-funding (runway "self-funding", passes).
  - Credit counts only from `credit_line`: confirmed, stated for this balance sheet (`as_of` within 45 days before it) and maturing more than 12 months after it; tagged undrawn capacity (`LineOfCreditFacilityRemainingBorrowingCapacity`, IFRS `UndrawnBorrowingFacilities`) is shown, never counted (no maturity). The runway is shown with credit and cash-only (D-M04-86).
  - 12-month debt: `DebtCurrent` (commercial paper inside, never added), else `LongTermDebtCurrent` + `ShortTermBorrowings`, else either alone or commercial paper alone; at a fiscal year end the larger of that and the year-1 maturity tag; with no current-debt tag, the latest annual schedule's year-1 within a year (labelled). No debt tags → wall "not tested" (optional input). 24-month wall = 12-month debt + year-2 of the latest schedule, shown.
  - Legal facts: open Part 3 events with item 1.03, 2.04 or 3.01 (fail or warn as their state); other open events listed, not gate triggers; an open 4.02 warns ("inputs under non-reliance"); an unfiled overdue period → incomplete + exit warning. Cash and investments above total assets → "withheld" (incomplete).
  - Signals: `survival_gate`, `runway_q`, `maturity_wall`, `distress_score`, `fcf_burn`, `debt_to_revenue`, `net_debt_ebitda`, `negative_equity`; `as_of` = the newest input's filing date (the due date when overdue). Review items open on a turn and are withdrawn when the condition ends (D-M04-88).
  - Scope readings for the open question below: liquidity-only (`asset_treasury`, `reit`) tests the wall, legal facts and filing status, the runway shown only; trust only (`spac_shell` periods) reads the trust account (`AssetsHeldInTrust…`; pass when stated, incomplete when not) plus legal facts and filing status. Open for the owner.

### How M01 reads M04 (D27; D-M04-58 = D-M01-5; rule 4 per M01 rule 4 and S6.14)
"Yes" in the rule-4 column is an exit warning: a warning only, the owner decides (D16).

| M04 output | Rule 3: later tranches | Rule 7: strength beyond 2σ | Rule 4: exit warning |
|---|---|---|---|
| CYCLICAL_TROUGH, gate pass or warn | Allowed | Yes (gauge not required, D-M04-62) | — |
| NO_SLOWDOWN, gate pass or warn | Allowed | No | — |
| AMBIGUOUS, STUMBLE | Blocked until the owner resolves the `m04_cvd` item; the answer becomes the state (D-M04-56, -58) | No | — |
| CYCLE_PLUS_DAMAGE | Blocked (D-M04-58) | No | Yes (M01 rule 4; S6.14) |
| STRUCTURAL_DECLINE | Blocked (D-M04-58) | No | Yes (M01 rule 4; S6.14) |
| Stale (carried state) | First tranche may use it; later tranches wait (D-M04-61) | As the carried state | As the carried state |
| Overdue | Blocked (D-M04-58) | No | Yes (D-M04-61) |
| Gate fail | Blocked (D-M04-31) | No | Yes (S6.14) |
| Gate incomplete or not applicable | Blocked; missing inputs listed (D-M04-35) | No | — |
| Capex-funded review open (< 6 quarters) | Allowed | No (D-M04-38) | — |
| `guidance_removed` (S1.7) | — | — | Yes: M01 rule 4's "quietly removed targets" (R19) |
| Red-flag warnings (`distress_score`, `financing_pressure`, non-reliance, others) | Shown; never block adds (D8, D-M04-21, -60) | No effect | Listed in the `exit_warning` reasons; never block (D16, D-M04-21) |

## Red flags
**Routing.** Tag first (D-M04-8), then the owner-confirmed stage (D-M04-46): introduction → young set; growth → young set + SG&A rule; mature → mature set; decline → mature set, reversion prior unused; confirmed shake-out → all-stage flags only. Unconfirmed stage → both sets, labelled, uncounted (D-M04-7).
**D13 column.** *now* = counts once D13 weights exist (confirmed R12 warnings, young per-unit flags; never while the stage is unconfirmed, D-M04-45); *≥ 20* = shown and reviewed, no weight until ≥ 20 owner-labelled episodes (D-M04-45, -60; labels per D-M04-73); *info* = information row, no vote until Part 8 (D-M04-11); *never* = screen only.

### Earnings quality (outline Red Flag 3; GE case, R11)
| Flag | Trigger | Routing | Output | D13 |
|---|---|---|---|---|
| `eq_cash` CFO/NI | 3-year CFO/NI < 0.8† (D-M04-20) | Warn: mature, decline. Note: introduction, growth, shake-out. NI ≤ 0 or below 1% of revenue → not meaningful (S2.1); `asset_treasury` not meaningful | Persistence warning, no return weight (D-M04-14) | ≥ 20 |
| Cash-flow accruals | Against own history | All stages | Shown, no warning (D-M04-20) | never |
| `contract_asset_gap`, `deferred_rev_gap` | Contract assets > 10 pp† faster than revenue in 2 readings; deferred revenue falling while revenue grows (S2.2) | Stage-neutral (D-M04-20) | Watch | ≥ 20 |
| `mscore` | SGI = 1 version > −1.78; only the raw M above → "growth-driven" note (D-M04-14) | Stage-neutral; GM ≤ 0 or `asset_treasury` → not meaningful | `m04_mscore` review | never (screen) |
| `misstate_f` | Bands > 1.00 and > 2.45 shown | Stage-neutral | Never a trigger (D-M04-14) | never |
| `restatement` | 8-K 4.02; dei error flag; 10-K/10-Q text (little r → note); 4.01 within 12 months escalates (D-M04-15) | Stage-neutral | Warning; open 4.02 marks rows "inputs under non-reliance" (D-M04-21) | ≥ 20 |
| `restate_delta` walk | Residual > 0.5% and > $0.1M† after the ordered labels (D-M04-16); `cf_shift_up` watch | Stage-neutral | `m04_restate` review | ≥ 20 |
| `estimate_share` | < 10% note, 10–25% watch, ≥ 25% elevated†, both directions; 3 years same direction adds a flag (D-M04-17, S2.7) | Denominator on the amount's basis; ≤ 0 or < 1% of revenue → not meaningful (D-M04-18) | ≥ 10% → `m04_estimate` review | ≥ 20 |
| `special_items` | Restructuring, impairment, write-down tags or "non-recurring"/"one-time" wording in ≥ 3† of 4 years; cumulative size vs operating income; stated non-GAAP gap quoted, never computed (D-M04-19) | All stages | Warning | ≥ 20 |

DSO and its alert are M02's (`financing/credit.dso`, `m02_fin_alert`, D-M02-45, -47). M04 shows DSO as context and raises no second alert for it; the DSRI inside `mscore` stays a screen.

**Built (Part 6; choices in M04_BUILD_LOG "Notes per part" → Part 6).** `financials/quality.py` (scores), `estimates.py`, `special.py`, `quality_step.py` (local pass after Part 7a's in the refresh; `run_financials.py quality`), `quality_view.py` + `tabs/_m04_quality.html`. Every input is the value as first reported, with tag and accession (D-M04-90). M-score: incomplete when an input is missing (checked first), not meaningful on gross margin ≤ 0 or `asset_treasury`; depreciation, else D&A; SG&A, else S&M (or marketing) + G&A, else G&A only; total liabilities derived from liabilities-and-equity − equity incl. NCI; optional balance-sheet lines per D-M04-90. `misstate_f`: Dechow Model 1; `issue` = any equity or debt proceeds in the year (M02's financing roles plus stock-plan tags, D-M04-90). CFO/NI: 3-year sums with the operating basis applied per year (D-M04-91). Contract and deferred-revenue readings on fiscal years; any tag change between two values = "definition changed" (D-M04-91). Estimate sentences, denominators by filing version and recurrence per D-M04-92; `special_items` and the review kinds per D-M04-93. GE and Lockheed are reference rows (no items, no signals).

### Dilution and financing (outline Red Flags 2, 3 SBC)
| Flag | Trigger | Routing | Output | D13 |
|---|---|---|---|---|
| `net_issuance_yoy` | Log change in basic weighted shares, same quarter a year apart, one filing; cover check (D-M04-22) | Not meaningful across IPO, de-SPAC, recast | Value | info |
| `issuance_pct` | Yearly percentile, float ≥ $700M, SIC 6770 out; top quintile = extreme (D-M04-23); serial = extreme in ≥ 2† of 3 years or a top-quintile 5-year composite (D-M04-26) | All | Band label | info |
| `financing_pressure` | Extreme or serial issuance **and** gate fail or warn now or in any of the 4 quarterly filings before the jump; cover counts tested too (D-M04-25, -26) | Gate fail → warn at every stage; gate warn → warn for mature, shake-out, decline, `m04_dilution` review for introduction, growth (D-M04-27). `issuance_funded` passing outside the warn band, `asset_treasury`, `reit` → review; `fund`, `financial` excluded; `spac_shell` not meaningful (D-M04-13, -25) | Warning. Non-cash cause (share-paid acquisition, IPO/de-SPAC recast, split, 3.03) → information; cash raises keep the warning, cause shown (D-M04-28). One condition alone → information | ≥ 20 |
| Shelves, ATMs, 424Bs | Fee-exhibit amounts; a shelf is capacity, resales add no shares (D-M04-24) | All | Information | never |
| Overhang | Convertibles, warrants, mandatory convertibles from verified text (S3.6) | All | `m04_overhang` review; information | never |
| SBC block, rating actions | SBC ÷ revenue and ÷ OCF, buyback offset (S3.4); actual or review rating sentences (S3.7) | All | Information; `m04_rating` review | never |

Buybacks, tax withholding, equity issued and debt raised or repaid come from M02's allocation block (`moneyflow/allocation.py`, `fin_tag_map`, withholding kept separate, "partial: X% mapped" label; D-M02-31); M04 does not map those tags a second time.

### Distress and FCF burn (outline Red Flags 1, 4, 6)
| Flag | Trigger | Routing | Output | D13 |
|---|---|---|---|---|
| `distress_score` | Z (SIC 2000–3999), Z'' otherwise, Ohlson O, in the distress zone (D-M04-31) | Stage-labelled; FF12 group 11 skipped; `asset_treasury` not meaningful | Warning; in distress while the gate passes → `m04_score_gap` review (S4.8) | ≥ 20 |
| Red Flag 1 row | Burn (runway warn or fail, or FCF on total capex < 0) and market share up < 1 pp† (D-M04-30, -68) | All stages; never a gate input | Warning; "missing: no share data" | ≥ 20 |
| `fcf_burn` | TTM FCF ÷ revenue and ÷ liquidity, operating vs capex-funded, `capex_split` context (D-M04-39) | All | Information; threshold at Part 8 | info |
| `debt_to_revenue`, net debt ÷ EBITDA | Against own 3-year range and peer z (D-M04-29) | All | Information | info |
| Negative equity | Equity < 0 with an accumulated deficit, TTM operating loss or negative TTM OCF; buyback-funded → note (S4.8) | All | Warning | ≥ 20 |

### Unit economics and margins (R11, R12; outline Red Flags 1, 5)
| Flag | Trigger | Routing | Output | D13 |
|---|---|---|---|---|
| R12 episode | TTM revenue up and GM down ≥ 3 pp† YoY in 2 straight quarters (reported; ex-stated-items beside); closes after 2 non-qualifying quarters (D-M04-40) | Every stage | One `m04_margin_cause` item; code tags cause sentences with a sum check, owner confirms, Gemini on request (D-M04-41) | — |
| `r12_warning` | Confirmed cause: price, mix or competition → warning + CvD Q2 vote; volume, input cost, FX → watch; one-off, accounting, segment, credits → cleared, fed to the `special_items` recurrence count (D-M04-44) | Every stage | Warning / watch / cleared | now |
| `inventory_sales_gap` | Inventory growth − sales growth > 15 pp† (S5.6) | Every stage (D-M04-7) | Warning | info until calibrated (D-M04-45) |
| Young per-unit flags | Unit GP not improving over 4† quarters while units rise; unit cost not falling with cumulative units; revenue per unit falling while unit cost is flat (S5.6) | Introduction, growth | Warning; a stated per-unit figure shown first | now |
| Burning with falling units | TTM units fall while FCF (total capex) < 0 (D-M04-47) | Introduction, growth | Warning; feeds the Red Flag 1 row | disputed (see Open questions) |
| `production_gap`, `credit_share_of_gp` | Production/delivery gap > 10%†; credits ≥ 50%† of GP, else dollars shown (S5.5) | Introduction, growth | Warning | info until calibrated |
| `sga_vs_revenue` | SG&A growth > revenue growth for 4† quarters (S5.6) | Growth, mature, decline (D-M04-46) | Warning | info until calibrated |
| Positive margin rows | `gm_trend_pp`, `opex_vs_sales` on reported and "excluding stated items and credits" bases; reversion prior shown, "not used" in decline (D-M04-48) | All | Information | info |

Negative gross margin alone is not a flag (S5.6). Contribution margins are company-stated only, labelled non-GAAP (S5.8).

**Built (Part 7a; data only, no signals — the rows above read it in 7b).** `fact_dim` from filing instances (customers, segments, products or services, classes of stock; recasts and segment-set changes listed, never merged; a renamed segment member whose overlapping values agree within 1% is continued; customers count customer shares of revenue from the year's own annual report (consolidated fact first, else one segment-tagged share, labelled; receivables, supplier and aggregate members left out, with reasons in the log)) and `unit_metric` (Tesla DS2 table by model line with prior quarter and year ago; production/delivery and billable-unit sentences with a stated period; regulatory credits as their own `credit` rows; company-stated non-GAAP gross profit with its release's own prior-year column) (D-M04-42). A year = stated, else the sum of 4 stated quarters, labelled; an approximate stated year ("over 1.8 million") yields to an exact sum. A new or renamed model line opens `m04_unit_kpi` (group 6). RIVN enters by UI promotion (D-M04-81); tracked names get no instance reads (D-M04-80). Choices: M04_BUILD_LOG "Notes per part" → Part 7a.

### Customers and RPO (D-M04-1 customer row)
| Item | Rule | Output | D13 |
|---|---|---|---|
| Stickiness class | Engine proposes (contracted: RPO ÷ revenue ≥ 0.5†; design-in: a ≥ 10% customer or an M02 link, SIC 3570–3679; else transactional); owner confirms (D-M04-43, S5.13) | Setup / `m04_customer` | — |
| Design-in loss signal | Agreement ended (customer-named 8-K 1.01/1.02; 1.02 co-filed with 2.03 = financing unless a customer is named); share below own 3-year minimum while revenue is flat or down; replacement supplier named | `m04_customer` review; "weakening" only after owner confirmation (D-M04-43) | via CvD Q2 |
| Contracted RPO | Below its 3-year minimum for 2 quarters → weakening; an RPO ÷ revenue break alone → review (D-M04-49) | Q2 vote | via CvD Q2 |
| Weight | min(1, at stake ÷ 0.25†); contracted 1; transactional 0; missing excluded (D-M04-50) | `customer_at_stake`, `customer_hhi` shown | info |

Sentence sources include M02's `supply_link` (L2 sentences with revenue share, L3 Item 1.01 counterparties, confirmed direction, each with its date; D-M02-36, -40), and the RPO series is M02's (D-M02-19 (4)). M04 adds only the loss rules and the class logic (D-M04-43, -49).

### Core trend information rows (outline "Analyze the financials" 1–4)
`rev_yoy`, `rev_cagr3`, `fcf_growth` (on total capex and on owner earnings = OCF − maintenance capex − SBC), `gm_trend_pp`, `opex_vs_sales`: each against own history and as peer robust z; near-zero bases → not meaningful (S2.1); no vote in CvD or confluence until Part 8 (D-M04-6, -11).

**As built (Part 1b; choices in M04_BUILD_LOG "Notes per part").**
- *Capex (D-M04-3, -78):* the company-definition row is M02's shown actual (`moneyflow/actuals.py`); total capex = the definition (PP&E payments, or the broader productive-assets tag incl. NVIDIA's FY2013–21 extension read from instances) that covers more of the displayed window (the last 8 fiscal years with capex; tie → PP&E tag; Part 1b live check 1: Amazon's older PP&E-tag years no longer push FY2018–25 onto "definition changed"); a year on the other definition reads "definition changed" and is not scored; fiscal-year values only at the company's year end.
- *Split (D-M04-6):* rung chosen on the latest year of an 8-year window (depreciation, else D&A; disclosed and project-level have no finder yet), capped at total capex, "not split" where the rung's fact is missing; Greenwald (five prior yearly PP&E ÷ revenue ratios, net and gross) shown only inside 0…total capex, with "out of range in n of m years"; "useful-life change?" when depreciation falls ≥ 20%† while gross PP&E grows. Rows: FCF on total capex, FCF on maintenance capex, owner earnings (information).
- *Trends:* TTM when a TTM a year earlier exists, else fiscal years; opex = gross profit − operating income; gross profit derived from cost of revenue where untagged, labelled. ROIC per S6.5 on fiscal years; debt and short-term-investment terms without a fact are taken as none and named; display only until Part 8a.
- *Guidance record (D-M04-10, -79, -84, -85):* `guidance/record.py`, stored in `guidance_outcome`; scored on the latest guide before period end (owner > release > call on the same day); direction-aware (D-M04-84): revenue, margins, EPS, income and capex miss below the low end, cost metrics (operating, total expenses, cost of revenue) miss above the high end, tax rate and other income unscored "not a performance target"; capex scored only on an exact M02 recipe, else "unscored: capex recipe approximate (<clause>)"; only core-family removals (revenue, gross margin, EPS, operating income, net income, capex, FCF) count as removed or expired and feed `guidance_removed`, others read "dropped (information)" (D-M04-85); GAAP actuals first-filed, "unspecified" basis scored on GAAP and labelled, non-GAAP missing until a reconciliation store exists; not-ended periods `pending` with M02's freshness state (extended to every metric family); removals per release against the same fiscal quarter's release a year earlier, reason searched in this and the prior release and calls.

## Signals out
Every row: `cik` (key; ticker for display, D-M04-74), one row per timeframe, `value` for numbers, `value_text` for states with `value` NULL, missing = both empty and `method` = "missing: <reason>", `evidence_grade` = weakest deciding input, `source_ref` = newest accession "+N", full inputs in `method` (D-M04-9). ✓ = may carry weight once D13 weights exist, subject to the red-flag D13 column; info = weight 0. One computation serves all timeframes; profiles differ in weights and, later, in persistence windows; profile parameters are recorded in `method` (S1.5). M04's own windows are fixed (3 years: D-M04-29, -49, -64). * = name proposed at the redraft, confirmed at build (Open questions).

| Signal | value / value_text | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| `cvd_state` | text: CYCLICAL_TROUGH, CYCLE_PLUS_DAMAGE, STUMBLE, STRUCTURAL_DECLINE, AMBIGUOUS, NO_SLOWDOWN | CvD class | ✓ | ✓ | info |
| `cvd_confidence` | 0–1 | Lower of the two winning shares | ✓ | ✓ | info |
| `cvd_coverage_q1`*, `cvd_coverage_q2`* | 0–1 | Present ÷ applicable rows | info | info | info |
| `deeper_than_peers` | text flag | Shared slump, company far below peers | ✓ | ✓ | info |
| `f_quality` | 0–5 | Q2 health vote | ✓ | ✓ | info |
| `f_score`, `g_score` | int (G: n of 8 in `method`) | Shown, not voted (D-M04-53) | info | info | info |
| `normalized_ep_cur`*, `normalized_ep_cyc`* | $; text "not used: <state>" | NEP on current and cycle-average revenue | info | info | info |
| `overreaction_gap` | pp | Price change − NEP change, 4 quarters | ✓ | ✓ | info |
| `market_share_chg_pp`* | pp; grade B or A | Q2 share row | ✓ | ✓ | info |
| `guidance_hit_rate` | % (0–100); n, misses, revisions, "repeated" in `method` | Q2 guidance row; built Part 1b (as_of = newest actual's filing date) | ✓ | ✓ | info |
| `guidance_removed` | text: removed / expired | Quiet removal event (S1.7); one row per release date, metrics in `method`; built Part 1b | info | info | info |
| `customer_signal` | text: intact / weakening / info | Q2 customer row | ✓ | ✓ | info |
| `customer_at_stake`, `customer_hhi` | share; index | Disclosed customer exposure | info | info | info |
| `lifecycle_stage` | text: stage, "unconfirmed" | Routing only; owner-confirmed stage (date, flag set) or "unconfirmed" (computed stage and review reasons in `method`); missing "not applicable (<tag>)" for `fund` / `financial`; as_of = newest cash-flow filing; built Part 1c | info | info | info |
| `filing_status` | text: current / stale / overdue; days in `method` | Filing age; built Part 1a (as_of = filed date, period end or due date) | ✓ | ✓ | ✓ |
| `shares_cover` | shares (all classes, split-adjusted); classes and tag in `method` | Cover count on its cover date (D-M04-2); built Part 1a | info | info | info |
| `implied_float_shares` | shares; float, close and date in `method` | Float ÷ close, yearly, "implied" (D-M04-2; M07 owns R22); built Part 1a | info | info | info |
| `survival_gate` | text: pass / warn / fail / incomplete / not_applicable | Gate verdict; trigger or missing inputs in `method`; built Part 4a | ✓ | ✓ | ✓ |
| `runway_q` | quarters (with confirmed credit; cash-only and both bases in `method`), or text "self-funding"; tier, capex-funded review and raised share (S4.13) in `method`; built Part 4a | Runway at D-M04-32 burn | ✓ | ✓ | info |
| `maturity_wall` | ratio | (12-month debt + 4 × burn) ÷ liquidity; 24-month wall in `method`; built Part 4a | ✓ | ✓ | info |
| `gc_language`, `covenant_status` | text class + quote | Latest text class | ✓ | ✓ | ✓ |
| `distress_score` | float; zone (distress / grey / safe) or `not_meaningful` in text; variant, X terms, close date, Z'' beside Z, Ohlson O in `method`; built Part 4a | Z, Z'' warning | ✓ | ✓ | info |
| `eq_cash`, `eq_accruals` | `eq_cash`: 3-year CFO/NI; text ok / warn / note / warn_or_note (stage unconfirmed) / not_meaningful. `eq_accruals`: (NI − CFO) ÷ average assets; text above / within / below own range, short_history | Cash conversion, accruals; built Part 6 (as_of = latest annual report's filing date) | ✓ | ✓ | info |
| `contract_asset_gap`, `deferred_rev_gap` | pp (latest reading's gap); text watch / none / definition_changed / short_history | GE pattern; built Part 6 | ✓ | ✓ | info |
| `mscore`, `mscore_sgi1`, `misstate_f` | float; text review / growth_driven / below / not_meaningful (`mscore`), above_cut / below_cut (`mscore_sgi1`), above_2.45 / above_1.00 / below_1.00 (`misstate_f`); incomplete = missing row | Screens; built Part 6 | info | info | info |
| `restatement` | text: none / little_r / dei / 4.02 / escalated (the most severe in 3 years); sources and counts in `method` | Error event; built Part 3 (as_of = newest evidence, else the latest periodic filing) | ✓ | ✓ | ✓ |
| `non_reliance` | text: open / none | Open 4.02 mark (`restate.non_reliance(cik, period_end)` gives the row mark later parts show); built Part 3 | ✓ | ✓ | ✓ |
| `restate_delta` | largest open residual in % of the old value; text: review / watch / explained / none | Walk steps filed in 3 years; an owner "explained" answer releases a step; built Part 3 | ✓ | ✓ | info |
| `estimate_share` | % (largest in the latest annual report); text note / watch / elevated / not_meaningful / none, "+recurring" when 3 disclosures agree | Profit from estimate changes; built Part 6 | ✓ | ✓ | info |
| `special_items` | ratio of cumulative tagged items to operating income (4 years); text warn / none / short_history | Recurring "one-time" charges; built Part 6 | ✓ | ✓ | info |
| `net_issuance_yoy` | log change | Issuance | ✓ | ✓ | info |
| `issuance_pct` | 0–100; band in text | Percentile | ✓ | ✓ | info |
| `composite_issuance_5y`, `sbc_offset`, `financing_capacity`* | log; ratio; $ | Context | info | info | info |
| `overhang_gross_pct`, `overhang_net_pct` | % of basic shares | Overhang | ✓ | ✓ | info |
| `financing_pressure` | text: warn / review / info / not_meaningful | Dilution to survive | ✓ | ✓ | ✓ |
| `burn_no_share_gain`* | text: warn | Red Flag 1 row | ✓ | ✓ | info |
| `negative_equity` | text: warn / note / none; built Part 4a | S4.8 | ✓ | ✓ | info |
| `fcf_burn`, `debt_to_revenue`, `net_debt_ebitda` | ratio (`fcf_burn`: TTM FCF ÷ revenue, tier in text; `net_debt_ebitda`: text `not_meaningful` when EBITDA ≤ 0); built Part 4a | Information rows | info | info | info |
| `r12_episode` | text: open / closed | R12 trigger | ✓ | ✓ | info |
| `margin_cause` | text class; stated $M in `method` | Confirmed cause | ✓ | ✓ | info |
| `r12_warning` | text: warn / watch / cleared | R12 outcome | ✓ | ✓ | info |
| `gm_delta_pp`, `gm_delta_pp_ex_items`, `inventory_sales_gap` | pp | Margin and inventory | ✓ | ✓ | info |
| `unit_gp`, `unit_gp_ex_credits`, `unit_gp_trend`, `unit_cost_vs_cumulative`, `rev_per_unit_vs_cost`, `units_falling_burn`* | $ per unit; text flag | Young unit economics | ✓ | info | info |
| `production_gap`, `credit_share_of_gp`, `sga_vs_revenue` | %; ratio; text flag | Young / growth flags | ✓ | ✓ | info |
| `rev_yoy`, `rev_cagr3`, `fcf_growth`, `fcf_growth_oe`, `gm_trend_pp`, `opex_vs_sales` | ratio (growth) / pp; text `not_meaningful`; own history and peer robust z (n, method, gap) in `method` | Core trends; built Part 1b, peer z Part 2 | info | info | info |
| `capex_maint`, `capex_growth`, `owner_earnings` | $; rung and total-capex tag in `method` | `capex_split` context, latest fiscal year; built Part 1b | info | info | info |

## Review queue (D8)
- **Order** (D-M04-71): 1 survival · 2 CvD review (AMBIGUOUS; also STUMBLE and CYCLE_PLUS_DAMAGE, Classification) and stage changes · 3 events · 4 restatement · 5 dilution · 6 margin, customer, unit KPI · 7 estimate and M-score.
- **Cap:** 5 judgment items per Monday–Sunday week (UTC) across M04†, the week as in D-M02-18 (S4.8); overflow listed on the M04 tab, flushed by order, oldest first (as D-M02-53). Gate fails are alerts and operational items are uncapped.
- **How alerts reach the owner:** `m04_gate_fail` items and exit warnings are listed in the existing end-of-run summary box (shown after the lock is released, D-M02-18, -53, -57) and on the M04 tab; the logon catch-up has no other channel.
- **Baselines:** existing hits are baselined except items filed in the last 12 months and a current gate fail or incomplete (D-M04-71); EFTS history is shown, never queued (D-M04-34).
- **Setup batch** (stages, peer shortlists, credit lines, gate inputs) is outside the cap and comes before Part 3 (D-M04-71).

| Kind | Opens on | First run | Steady state |
|---|---|---|---|
| `m04_gate_fail` (alert) | Gate turns fail or incomplete (D-M04-71); fail-class text | 0 | Rare |
| `m04_gc_text` | Alleviated, audit-matter, IFRS uncertainty; hypothetical when runway < 8 | History baseline only | < 1 a quarter |
| `m04_covenant` | Waived or reset covenant; current-debt jump above roll-down (sub-class `m04_current_jump`) | Baseline | < 1 a month |
| `m04_runway` | Capex-funded runway < 6 quarters (D-M04-38); name confirmed at Part 4a | 0–1 | Rare |
| `m04_score_gap` | `distress_score` in distress while the gate passes | 0–1 (BA Z 1.53) | Rare |
| `m04_credit_line` (operational) | Text-found undrawn credit to confirm (runway < 12 or capex-funded warn) | ~2 | Per 10-Q for those names |
| `m04_gate_input` (operational) | Non-financing gate input tag to map (financing tags go through M02's `fin_tag_map`, D-M02-31) | 1 (INFQ) | Rare |
| `m04_cvd` | CvD AMBIGUOUS, STUMBLE or CYCLE_PLUS_DAMAGE; the owner's answer becomes the state (D-M04-56) | Set at Part 8a | ~2–4 a year (estimate) |
| `m04_stage` | First stage; computed change; ambiguous | 15 (setup) | 4–5 a year |
| `m04_peer` | Ranked SIC shortlist | ~13 (setup) | New names only |
| `m04_event` | 8-K 4.02, 4.01, 2.04, 3.01, 1.03, 2.06; NT filings | Last 12 months only | ~2 a year |
| `m04_restate` | Unexplained residual above tolerance | ≤ 4 | 2–3 a year |
| `m04_dilution` | Per `financing_pressure` routing | 1 (MSTR) | 4–8 a year with overhang |
| `m04_overhang` | Instrument terms from verified text | ~10–11 (MSTR 7 incl. STRE; INFQ, INTC, BA) | 0–1 per new 8-K or 424B |
| `m04_financing_doc` | ATM or resale found without fee exhibit or count | A few | 0–1 |
| `m04_rating` | Actual or review rating sentence | 1 (INTC) | 0–1 |
| `m04_margin_cause` | R12 episode opens | Per Part 7b scan | 1–3 a year |
| `m04_customer` | Design-in loss signal; RPO ratio break; customer-named 1.01/1.02 | Per class confirmation | 1–3 a quarter (unmeasured) |
| `m04_unit_kpi` | New unit label or category break | — | ~1 a year |
| `m04_estimate` | Estimate share ≥ 10% | Part 6 scan | ~1–2 a year (inference) |
| `m04_mscore` | M (SGI = 1) > −1.78 | 1 (NVDA FY2026) | ~1 a year |

Merged steady state: about 25–55 items a year (0.5–1.1 a week); the cap absorbs the high end (BP gaps #5). All volumes except events, walk steps and EFTS hits are estimates until each part logs.

## Failure modes
D9: how could this data mislead? Build and operations rows (lock, logon load, fixtures, DB growth) are in M04_BUILD_LOG.md.

### Data layer
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Point-in-time values and tag switches | Recasts rewrite what was known (Rite Aid FY2017 32,845 → 22,928; WDC FY2023 12.3B → 6.3B); 8-K and DEF 14A facts become "latest"; a tag switch (ASC 606 contract tags) reads as a change | `facts_as_of`, periodic forms only, first-filed values in backtests (S1.1, S6.1); switch inside a window = "definition changed", not scored (D-M04-3; S2.2) |
| Extension-only, wrong-meaning and mis-mapped tags | Values only under extensions, absent from companyfacts (NVDA capex before FY2022, NVDA marketable securities 51,951; MRVL has no issuance tag); GE FY2016 contract assets double-tagged as `CommodityContractAssetNoncurrent` (a derivative concept); nonproduction D&A read as total (INTC $200M vs $9,204M) | Instance read or "missing", never zero; per-company alias (GE only), that concept never mapped generally; `Depreciation` added, fallbacks marked (D-M04-3, -42; S1.3, S1.4, SB.18) |
| Shares | Cover and period-end dates mixed; multi-class counts missing (GOOG, META, MSTR, SPCX); splits | Four series; class-summed cover count from R1; split guard on every series; pre-2011 history on basic weighted average, labelled (D-M04-2) |
| Capex definition and split | Broader fallback tag (+15.8% Amazon FY2016) mixed into peer z; Greenwald out of range (MU 6 of 8 years, INTC 4 of 4) or calls a build-out maintenance (MSFT 65–79%); depreciation moves with useful lives (INTC 2023 −29.5%) | Display on M02's company-definition recipe (D-M02-29, -32) with a "broader tag: <what it adds>" marker, worded apart from M02's "≈, gap X%"; peers on PP&E tag only (NVDA, AMZN out); depreciation default capped at capex, Greenwald only as in-range cross-check; method tag on every value; consumers use total capex (D-M04-3, -6; S2.7) |
| History depth and breaks | XBRL starts 2009–2011, later for some concepts; bankruptcy emergence leaves no 12-month period (Peabody 2017) | Depth per concept; "insufficient history", never "first deep decline"; stubs never summed (D-M04-54) |
| De-SPAC and same-CIK history | Shell and target histories under one CIK read as restatement or issuance (INFQ FY2025 loss 52% smaller; SPCX +100%, INFQ +1,310%) | Boundary at the closing 8-K (2.01 + 5.06); `predecessor` label; `spac_shell` keyed on period end (D-M04-8, -22) |
| Filer status and deadlines | Status must carry year to year: Invitae's FY2022 float $569.8M is above the $560M exit line, so it stayed large accelerated; an entry-line ($700M) reading misdates its deadline | Rule 12b-2 entry and exit lines from stored float, carried yearly; longest deadline when float is missing; Invitae as regression case (S1.6; D-M04-36, -61) |
| Foreign filers | 6-K XBRL stops (GFS); IFRS wording; 6-Ks carry no item codes, so default and delisting notices go undetected; a filer can slide a year unseen | IFRS phrases; annual burn up to 16 months, then incomplete; "as of <date>" labels; 6-K events a known omission (D-M04-36) |
| Tickers and prices | Recycled tickers attach another company (BBBY, RAD, SHLD); spliced series (BTU 2017, CHK 2021); stale bars after cancellation (RADCQ, NVTAQ to 2026-10-09) | `cik` on every signal; Tiingo symbol only when name and dates match the SEC company; last real trade found first; else "missing: no prices" (D-M04-72, -74) |
| Signal record | Text in numeric `value` sorts above numbers; missing stored as 0; transcript or owner-entry rows look like filing evidence | `value_text`; missing = "missing: <reason>"; grade = weakest deciding input, inputs listed in `method` (D-M04-9) |
| Segment data | Segment figures read as consolidated (the Rivian "recast" mistake); segment definitions restated | `fact_dim` with axis and member on every value; breaks flagged, not merged (D-M04-42) |

### Peers
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Peer set | Coarse or stale SIC (solar in 3674; AMZN's SIC peers are mail-order retailers); product peers outside SIC (QCOM, WDC); 505 names in 3674; a 10-K-only "active" filter drops 20-F filers (GFS); non-SEC peers (SK hynix, Samsung) missing; acquired revenue reads as growth (AMD +43.6% 2022) | Ranked shortlist, active = 10-K/20-F/40-F; owner confirms and adds product peers; non-SEC peers stored as "missing"; acquisition years flagged (R1 case list) (D-M04-4; S6.2) |
| Period offset and peer lag | The cycle turns inside a 1–2 month offset; 53-week years add about 2%; the peer quarter arrives weeks later (WDC 32 days after Micron) | TTM ±45 days, quarters ±40; end dates shown; 53-week flag; outside = "no comparable period" (D-M04-5) |
| Robust z | The method flips the label with few peers (Intel 2022 at n = 4: −0.82 to −1.92); one outlier puts everyone "in the pack" (NVDA 2023 z +8.97); high dispersion hides a large gap (Intel 2025 −34.8 pp at z −0.91) | Fixed gap below 5; MAD × 1.4826 × b_n for 5–9; drop \|z\| > 3 once; method and n shown; gap in pp always shown; neutral zone between cycle and company-specific (D-M04-52, -55) |
| Margin comparisons | One unlike peer gives a fake gap (Micron vs WDC −33.5 pp); no gross-profit tag; cost of sales differs (Amazon fulfillment; Target rate on Sales) | Margin gap votes only with ≥ 3 comparable peers (S6.10); method `derived`, base stated, "not like-for-like" (D-M04-3, -40, -54) |

### CvD profile
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Activation | TTM lags: MU read NO_SLOWDOWN at its 2022-10-07 10-K; one lumpy quarter can switch CvD on | Revenue, gross margin (≥ 3 pp) or operating income (≥ 25%) falls, or latest quarter ≥ 10% below a year earlier (starting values) (D-M04-55, -67) |
| Missing rows | Unbuilt rows read as disagreement (all AMBIGUOUS) or vanish unseen; a state can rest on few rows (MU trough on 3 of 7) | Missing rows leave the denominator; ≥ 2 present; coverage shown beside confidence (D-M04-56) |
| Filing lag, stale and overdue | The price trigger fires before the filing that confirms the state (Micron's low came while filings showed growth); a dead company keeps its last state (Invitae, RadioShack) | "stale" once a period ends unfiled, later tranches wait (pauses up to 40–50 days); `overdue` → gate incomplete and exit warning; status re-evaluated on every logon run, not only on a new filing; 8-K 1.03 and 3.01 fail the gate first (D-M04-37, -61) |
| Inventory days | Write-downs understate days (Micron 153 vs 235); ending vs average inventory gives other figures (151/213) | One labelled definition (average inventory); write-down added back to inventory and COGS (R1 brief; probe L9) |
| Capex and intensity rows | One cut drives both Q1 supply response and Q2 weakening; a surge into falling revenue reads intact; a planned counter-cyclical build reads neutral | Q2 on total capex intensity and R&D level; surge > 1.5× own average → neutral, pointer to M05 (D-M04-54, -64) |
| Troughs and ROIC | 1–4 pp wiggles count as cycles (Intel 2013–17); write-downs fake lower lows; invested capital ≤ 0 after buybacks; goodwill jumps | 5 pp turning points, write-down adjusted; ROIC `not_meaningful` when ≤ 0 and "intact" only with gross margin (D-M04-54) |
| Health scores | 4 of 9 F signals are cycle-driven (MU FY2016 F = 3); G penalises acceleration (NVDA FY2024) and needs peer medians; F-quality's CFO point holds for a decliner (Intel 2025 intact) | F-quality 0–5 is the only health vote; Piotroski F and Mohanram G shown, not voted (D-M04-53, -59) |
| Equity point | Plan issuance every year reads as dilution; INTC 2024 (+2.1%) stays intact | Round 3 measure, lost only on extreme or serial issuance; unconfirmed stage → missing (D-M04-65) |
| Normalized earnings power | Assumes the next cycle resembles the last; decliners keep old margins; repeated "one-time" items inflate it; two unrelated one-offs both stay in | Current and cycle-average revenue bases; reported and ex-items shown; an item excluded only if nothing similar in 10 years (D-M04-54, -66) |
| Overreaction gauge | Mismatched windows fake an overreaction; clears near the low (MU Q2 FY23); a trough without overreaction still gets strength | Same 4 quarters for price and earnings; informs, never overrides (D-M04-57, -62) |
| Market share and the Intel case | Most names rest on owner entries (grade B); "no gains" line is illustrative; without share and moat rows CvD never says "damage" alone (Intel) | Grade shown; else "missing: no share data"; Intel AMBIGUOUS → owner review, the owner's answer is the expected state (D-M04-63, -68) |
| Guidance record | Seasonal guides read as removals (Intel January); Intel FY2022 a "hit" despite two cuts; release-silent guiders; a call not yet stored or a release not yet read looks like a removal (call-only guiders after each release); one capex guide scored two ways | Same fiscal position a year earlier; ended = "expired"; revisions counted separately; "missing (DS1)"; removal only in M02's "not restated" state, a `guidance_skip` refusal counts as the stated reason; capex actuals from M02's `guided.py` (D-M04-10; D-M02-29, -30) |
| M01 reading of CvD | A NO_SLOWDOWN name at a gate warn (Rivian) still gets tranches | Only CYCLICAL_TROUGH + gate pass adds rule-7 strength; gate state shown beside (D-M04-58) |

### Survival gate
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Distress scores (Z, Z'', O) | Young firms read "distress" with years of cash (Rivian Z'' −5.37 with $5.3B); Type II error 15–20%; bubble prices inflate X4; O-score units flip results; BA 1.53 at FY2025 | Out of the gate; stage-labelled `distress_score` warning; variant, version, cut-off and units stored and tested (D-M04-31) |
| Burn and runway | One-quarter swings and seasonal Q1 OCF (AMZN); one 10-Q gives no TTM (SPCX); growth capex makes cash-rich firms look short (AMZN 9.1, Intel FY2024 5.6); capex that cannot be cut only warns | Worse of TTM ÷ 4 and last two quarters; one quarter → incomplete; capex-funded names warn below 8, review below 6, never fail; rule-7 blocked while in review (D-M04-32, -38) |
| Undrawn credit | Revolvers mostly untagged; borrowing base and springing covenants cut availability; facilities expiring inside the horizon (Boeing FY2019: $3.2B 364-day ends Oct 2020 → 5.9 quarters, fail, not warn) | Confirmed credit only (tag, verified text or owner entry, with expiry) maturing beyond the horizon; Boeing 5.9 and 5.5 regression cases (D-M04-32; SB.18) |
| Debt maturities | `DebtCurrent` already holds commercial paper (Boeing FY2019 13,449 summed vs 7,340); roll-down looks like reclassification; 7 quarters' runway with 3.5 quarters' debt only warns | Commercial paper never added twice; 12-month debt > liquidity fails, + 4 × burn warns, 24-month wall shown; only text fails a reclassification (D-M04-33, -34) |
| Going-concern and covenant text | Hypotheticals, negations, alleviated cases, audit matters, boilerplate (Invitae Q2 2023) and SPAC-era sentences match; "in compliance" dominates; breaches are often waived; text leads by only 62–144 days | Sentence classes; only "exists", unwaived breach, forbearance or covenant reclassification fail; alleviated, waived or reset → warn + review; `spac_shell` periods out (INFQ) (D-M04-34, -8) |
| 8-K events | Cure notices usually end in compliance; a deficiency ending in delisting only warns until the final notice; listing transfers | 1.03 fails, never auto-clears; 2.04 fails until a clean periodic filing and owner resolution; transfer = information (D-M04-37; S1.11) |
| Gate scope | MSTR's assets and income swing with bitcoin; banks, funds and ETV never get tranche adds | Model tag → liquidity-only gate for `asset_treasury`, `reit`; "not applicable" reads as not-pass until a sector gate exists (D-M04-8, -35) |

### Earnings quality
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Cash conversion and accruals | Growth inflates accruals; CFO/NI meaningless near zero NI or with a sign flip; finance arms and discontinued ops (GE 2016); factoring pulls cash forward; a growth firm with real collection problems gets only a note | Cash-flow version vs own history, no return claim; `not_meaningful` when NI ≤ 0 or < 1% of revenue; 3-year sums; < 0.8 warns only for mature and decline (D-M04-14, -20) |
| Operating basis | Fair-value, crypto and valuation-allowance swings move NI without cash (Tesla 2023, MSTR 2025); the 21% / 35% tax approximation misses foreign and capital-loss rates | Operating basis; stated rate when given; model tag → `not_meaningful` (D-M04-8, -14; S2.1) |
| M-score and misstatement score | SGI penalises growers; old cut-offs; > 100 false positives per true one; GMI breaks on negative margins; misstatement `issue` ≈ 1 for large caps and soft assets lift most above 1.00 (Apple 1.30); a growth-based manipulator gets only a note | Screens only; review only when the SGI = 1 M-score > −1.78; misstatement score labelled "approximation", both bands, never a trigger; `issue` unknown → missing (D-M04-14; S2.3, S2.4) |
| Restatement events | No 8-K for little r; no history before 2004-08-23; dei error flag only on annual reports from 2023 and missed by out-of-period corrections (AVGO's Dec 2023 10-K needs its R1); a 4.01 after a de-SPAC is routine | 4.02 + dei flag + text + one-off old-filing fetch; flag never positive evidence; a 4.01 within 12 months escalates, post-de-SPAC 4.01 without disagreement = information (D-M04-15; S1.11) |
| Restatement walk | Recasts, adoptions, tag switches, rounding, cash-flow reclassifications and de-SPAC look like errors; a dollar floor hides small corrections; tiny residuals queue (GE +$4M on −$244M); early-XBRL data defects (flip-flops, period mix-ups, consolidated vs segment scope swaps) look like restatements | Data-defect labels first (explained, never review; Part 3 live check 1), then ordered labels, then residual > 0.5% and $0.1M → review; first-run baseline (D-M04-16, -71) |
| Open 4.02 | CvD, gate and scores read disowned figures; an M01 add can still trigger | Rows marked "inputs under non-reliance" and warn; adds not blocked (D8; D-M04-21) |
| Estimate changes | Disclosed only when material; income-decreasing ones exist; GE Power's 29% segment share hidden behind 15.5% company share | Bands in both directions on the amount's own tax basis; segment share only when stored or quoted (D-M04-17, -18) |
| Recurring "one-time" charges | A genuine multi-year restructuring reads as recurrence; a computed non-GAAP gap misstates the company's own | ≥ 3 of 4 years (starting value), shown with its plan; gap quoted, never computed (D-M04-19) |

### Dilution
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Share measure | Diluted counts move with the profit sign; splits read as 10× growth; escrowed shares sit in basic EPS but not the cover count (INTC 71M); counts filed in USD (INFQ warrants) | Basic weighted average, same-filing pairs; split guard; cause label on the cover cross-check; unit check → data defect (D-M04-2, -22) |
| Weighted-average lag | Late ATM sales show only partly (MSTR +28.1% weighted vs +35.5% cover); a raise repairs the gate before the shares show (BA 2024–25) | Cover-count cross-check; gate condition looks back 4 quarterly filings (D-M04-22, -26) |
| Legacy-share pairs | One filing mixes bases: INFQ's comparatives are unrecast legacy shares (× 0.3474 exchange ratio) beside recast figures | Not meaningful across a de-SPAC once the close is linked; a pair at the exchange ratio → data defect (D-M04-22) |
| Issuance bands | All-filer breakpoints set by microcaps; SPACs pass a float filter (95 SIC-6770 filers ≥ $75M) and the "blank check" phrase is no test (101 non-6770 hits); about 1,400 small firms read "extreme" | Float ≥ $700M with SIC 6770 excluded explicitly; yearly percentiles of same-filing pairs (D-M04-23) |
| Shelves, 424Bs, ATMs | A shelf is capacity, not a raise; 21 of 41 424Bs carry no fee exhibit; GOOG's June 2026 424B5s were equity, not debt; resales add no shares | Fee exhibit per 424B, else paired final supplement or cover; class by form and security; resale = supply, never dilution (D-M04-24) |
| Causes | Value-creating issuance warns (Intel 2025 strategic buyers); 8-K 3.02 absent below 1% (5% small filers) | Only non-cash causes become information; cash raises warn while the gate fails or warns, cause shown; share counts stay the measure (D-M04-28) |
| Warning routing | Issuance is MSTR's strategy; a funded plan in a brief warn band warns; a raise from strength after a brief warn warns; a growth firm with a sliding runway is only reviewed; an incomplete gate gives no warning | Model tag and gate state route it; cause shown; gate fail warns at every stage; incomplete shown as a data gap (D-M04-13, -25, -26, -27) |
| Convertibles, warrants, preferred, Up-C | As-converted only when dilutive; capped calls; stale or contingent warrants; preferred series missed (MSTR STRE, ~10–11 series); Up-C class A understates the share base | Text with quote → review; in the money only, gross and net; "missing: exchangeable units" (D-M04-25) |

### Unit economics and margins (R11, R12)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Life-cycle stage | Securities flows (AAPL shake-out); partner financing mimics growth (INTC, Tesla FY2024); one-year flips; acquirers look like growth; MRVL's latest-year shake-out not reviewed | Core investing, 2 of 3 years; CAGR conflict → review; owner confirms first stage and every change; unconfirmed → both flag sets, uncounted (D-M04-7, -12, -46) |
| R12 trigger | Stage-gated, Invitae would never be checked; a one-quarter charge fires it (Intel 2024Q3); companyfacts lacks Target's 10-Q cost of revenue for a year, so it fires late or never | Every stage; 2 straight quarters; ex-items basis beside; 10-Q instance read into `fact_dim`, else "missing: dimensional" (D-M04-40, -42) |
| Margin causes | Management framing, buried offsets, mis-signed summaries; Target 2022 warns, then reverts | Arithmetic check of stated components; quote stored; owner confirms; Gemini on request only; price, mix, competition warn, the rest watch or clear (D-M04-41, -44) |
| Stated items and credits | Management chooses what is "stated"; regulatory credits lift margin with no unit cost (Rivian Q4 2025); Target FY2023's rebound is reversion | Reported and ex-items-and-credits both shown; reversion prior shown, "not used" for decline (D-M04-46, -48) |
| Per-unit figures and KPIs | Revenue scope ≠ units (leases, credits, services); stated vs computed differ (Invitae $380 vs $394); production above deliveries flatters cost; KPI categories change; huge margins on tiny revenue | Stated figure first with quote, computed beside on matching scope; gap > 10% flagged; breaks flagged, not merged; `not_meaningful` below a revenue floor (D-M04-42) |
| Burning with falling units | Planned model changeovers warn | Young-firm warning only (D-M04-47); its D13 weight is disputed between D-M04-45 and -60 (Open questions) |

### Customers
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| ≥ 10% customer list and weight | Customers anonymous; matching across years is inference; a shorter list read as a loss (NVIDIA FY2026); a customer may have shrunk below the line; the 0.25 at-stake divisor is unsourced (a single 12% customer weighs 0.48) | Revenue at stake and total revenue shown; loss only with text or 8-K evidence and owner confirmation; weight a starting value, missing excluded (D-M04-43, -50) |
| RPO | Tiny for design-in suppliers (NVIDIA ≈ 1%); one counterparty dominates; flat RPO with soaring revenue only reviewed | RPO test for the contracted class only; ratio-only breaks → review; counterparty share as a dated company-stated note (D-M04-49) |
| 8-K 1.01 / 1.02 | Mostly financing (all four 1.02 + 2.03 co-filings on the watchlist) | Customer event only when the text names a customer or supply agreement; 1.02 co-filed with 2.03 = financing (D-M04-43) |

### Calibration and starting values
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Unsourced thresholds | Starting values (±40 days, 2 misses in 4, 3 pp, 25%, 10%, 8-quarter warn band, −25 pp) read as tested rules; names sit near lines (SPCX 7.997, AMZN 9.1) | Labelled starting values; tuned only at Part 8 (D-M04-45, -51) |
| Small, hindsight-prone labels | 24 + 4 CvD episodes and 20–30 red-flag cases are small; labels that know the outcome fit hindsight; J.C. Penney has no prices for the gauge | Blind labelling, split before and after FY2018; tune only activation, z cut, majority and gauge (D-M04-51, -72, -73) |
| Unweighted and information rows | A serial diluter with a passing gate can reach confluence; `debt_to_revenue`, net debt ÷ EBITDA, `fcf_burn` and core trend rows give no warning until calibrated (AMZN) | Red flags shown and reviewed with no D13 weight until ≥ 20 labelled episodes; information rows against own range and peer z (D-M04-11, -29, -39, -60) |
| Backtest results | Invite threshold edits inside a build | Changes proposed with sources at a High review (D6; D-M04-73) |
| First runs and backfill | Baselines flood the queue (101 walk steps, 136 EFTS hits); history exists only after the owner's backfill | Baseline recorded, not queued, except items filed in the last 12 months and current gate fails; weekly cap 5; missing until backfilled (D-M04-70, -71) |

### Owner entries and overrides
No decision in this review overrode a research recommendation. These rows cover owner-entered inputs and the owner's changes in D-M04-1.

| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Model tags | An untagged treasury company routes by SIC (MSTR 6199 excluded as a financial); a wrong tag removes tests | Hand-edited file with reason and source; unknown tag rejected; engine may propose `reit`, owner edits (D-M04-8) |
| Stage override | The owner's last confirmed stage keeps routing after the company changes | Computed changes and ambiguous cases reopen `m04_stage` (D-M04-7, -12) |
| Peer curation | Hand-picked peers can fake a shared or company-specific reading | Engine shortlist and each peer's end date shown; non-SEC peers listed as missing (D-M04-4, -5) |
| Owner-entered facts | Share, revolver and stickiness entries age and carry no filing | Grade B; expiry on credit entries; class proposed by engine, owner confirms (D-M04-9, -32, -43, -68) |
| D-M04-1 owner changes | IQR-based robust z is unstable with few peers; no research threshold exists for customer loss, so the owner's class decides the vote | z amended to MAD × b_n with fixed-gap fallback; "weakening" owner-confirmed (D-M04-43, -50, -52) |

## Decisions
- D-M04-1 (2026-10-06): CvD profile approved with owner changes — revenue gap scaled by peer dispersion (robust z); customer signal by stickiness class and own history, weighted by revenue at stake.
- D-M04-2 (2026-10-12, review 1.1a): Shares concepts — four series `shares_period_end`, `shares_cover` (on its own cover date), `shares_basic_wavg`, `shares_diluted_wavg`, plus `sbc`. Multi-class filers without a non-dimensional count (GOOG, META, MSTR, SPCX) get the class-summed cover count from the filing's R1 page (~37 requests for 3 years, then 1 per new filing in the logon refresh); older history uses basic weighted average, labelled. Float shares for R22 = `dei:EntityPublicFloat` ÷ close on its date, yearly, labelled "implied" (M07 owns R22).
- D-M04-3 (2026-10-12, review 1.2a): Capex definitions, one per use — display: the company's own definition (capex_definitions.toml, D-M02-29/-32) with the standard-tag value beside it and a visible "≈ broader tag" marker plus legend; own-history rows: the longest consistent tag series, a switch inside the window reads "definition changed" and is not scored; peer statistics: PP&E tag only, fallback-only peers (AMZN, NVDA from FY2022) listed "not like-for-like" and excluded. Closes the 2026-10-07 fallback-tag item.
- D-M04-4 (2026-10-12, review 1.3a): Peer discovery — engine proposes peers from 4-digit SIC (`entity.sic`, submissions `sic`) plus one owner-run browse-by-SIC probe per SIC; owner confirms or edits in `peer_group` via `m04_peer` items and adds product-market peers outside SIC (e.g. QCOM, WDC); non-SEC peers stored by name as "missing". Closes the SIC peer-discovery item (D19).
- D-M04-5 (2026-10-12, review 1.4a): Peer period offset — TTM ±45 days; quarters and instants ±40 days (starting values; calibrated in Part 8). Outside → "no comparable period", counts toward the < 5-peer fallback; each peer's end date shown, 53-week years flagged. Tightens D-SEC-9's 45-day match for M04 quarter and instant comparisons.
- D-M04-6 (2026-10-12, review 1.5a): Capex split (amends A2) — M04 owns `capex_split` in the data layer (Part 1), M05 reuses it. Ladder: disclosed → project-level → depreciation (default, capped at total capex) → D&A (marked as last rung) → "not split"; Greenwald shown beside it as a cross-check only when inside 0…total capex. One method per company for the displayed window, tagged on every value. Consumers (runway burn, FCF after SBC, Q2 capex row) use total capex; maintenance capex is information only ("owner earnings" = OCF − maintenance capex − SBC; "runway without growth capex"). M05 owns growth capex × ROIC (outline CAPEX 3–4). Why: Greenwald is out of range in 6 of 8 Micron and 4 of 4 Intel years, and calls 77.7% of Microsoft's FY2026 build-out maintenance. Risk kept as a failure mode: useful-life changes move depreciation (Intel 2023 −29.5%).
- D-M04-7 (2026-10-12, review 1.6a): Life-cycle stage (defines R2's "ambiguous stage"; replaces pack 5.1) — Dickinson signs (CFO, investing, financing) with **core** investing = capex + acquisitions − asset and business sale proceeds; a stage holds when 2 of the last 3 fiscal years agree. `m04_stage` review when no stage holds 2 of 3, the held stage is shake-out, or the stage conflicts with 3-year revenue CAGR (introduction/growth with CAGR < 0; mature/decline with CAGR > 20%, the OECD-Eurostat high-growth line, starting value). Fewer than 3 fiscal years → review; until confirmed both the young and mature flag sets are computed, labelled "stage unconfirmed" and not counted in D13 confluence. Until confirmed, the owner's last confirmed stage keeps routing. Owner override. Stage routes flags only: R12, inventory-vs-sales and the survival gate run at every stage.
- D-M04-8 (2026-10-12, review 1.7a): Owner model tags — six fixed tags in hand-edited `config/company_models.toml` (app never edits it; unknown tag rejected at load; one-line reason and source each): `issuance_funded`, `asset_treasury`, `reit`, `fund`, `financial`, `spac_shell`, with the routing table in docs/m04_review/R1_brief.md (asset_treasury: NI/accrual/M-score and Z "not meaningful", liquidity-only gate; reit: liquidity-only gate; fund/financial: excluded; spac_shell: trust only). A tag overrides SIC and applies before stage; untagged financials (FF12 group 11) read "not applicable"; the engine may propose `reit` for SIC 6798, owner confirms. Initial entries: MSTR `asset_treasury`, ETV `fund`, INFQ `spac_shell` for periods before closing (2026-02-13) and no tag after (owner).
- D-M04-9 (2026-10-12, review 1.8a): Signal record encoding (extends D13, binding on all modules) — migration adds `signal.value_text`; enums and states go there with `value` NULL, numbers stay in `value`; a missing signal is a row with both empty and `method` = "missing: <reason>" (never zero); one row per timeframe, ST "info" rows weight 0; `evidence_grade` = weakest deciding input (A filings and verified quotes; B transcripts, third-party share/trade data, owner entries without a filing); `source_ref` = newest accession, "+N" when more, full input list in `method`.
- D-M04-10 (2026-10-12, review 1.9a): Guidance record (Q2 row) — miss = actual below the low end of the latest range given before period end (or below a point guide) on the guide's own basis (GAAP from first-filed facts, non-GAAP from the stated reconciliation); point and "approximately" guides unscored until a tolerance exists; repeated = 2 misses in the last 4 guided quarters (starting value); downward revisions counted separately; removed = a metric family guided at the same fiscal position a year earlier is absent now with no stated reason (reason searched in the current and prior release and call), for a period not yet ended (ended = "expired"). Shared `guidance/` functions; M11 owns R19 scoring; M04's Q2 row reads `guidance_hit_rate`; release-silent guiders read "missing (DS1)".
- D-M04-11 (2026-10-12, review 1.10a, new): Core financial trends (outline "Analyze the financials" 1–4) as information rows — `rev_yoy`, `rev_cagr3`, `fcf_growth` (on total capex and on owner earnings), `gm_trend_pp`, `opex_vs_sales`, each against own history and as peer robust z; no vote in CvD or confluence until Part 8 calibration.
- D-M04-12 (2026-10-12, review 1.11a, new): Stage confirmation — the owner confirms each company's first computed stage once (setup batch, about 15), then only computed changes and ambiguous cases (about 4–5 a year). Restores pack 5.1a's guard (Tesla's financing-sign "growth").
- D-M04-13 (2026-10-12, review 1.12a, new): `issuance_funded` — normal survival gate; dilution is a review item only while the gate passes and runway is outside the warn band; in the warn band or on gate failure `financing_pressure` warns (outline Red Flag 2, dilution "to survive"). Supersedes the pack's liquidity-only gate for issuance-funded names (3.4a, Round 6 change 19); only `asset_treasury` and `reit` get the liquidity-only gate.
- Round 1 suggestions S1.1–S1.12 accepted (owner "rest ok"; texts in docs/m04_review/R1_brief.md), S1.10 with 15 `m04_stage` items at first run.
- D-M04-14 (2026-10-12, review 2.1a): Earnings-quality scores are screens — cash conversion (CFO/NI) and cash-flow accruals are persistence warnings with no return weight; Beneish M-score computed with and without SGI = 1, review only when the SGI = 1 version is above −1.78 (else a "growth-driven" note); misstatement F-score shown in both bands (> 1.00, > 2.45), never a trigger.
- D-M04-15 (2026-10-12, review 2.2a): Restatement sources — 8-K 4.02, the dei error-correction flag (R1 pages), 10-K/10-Q text (little r), plus a one-off fetch of at most ~35 older filings to label pre-corpus walk steps; an 8-K 4.01 auditor change within 12 months escalates.
- D-M04-16 (2026-10-12, review 2.3a): Restatement walk tolerance — after the ordered labels (standards, discontinued ops, segments, splits, tag switches, rounding, NCI share, restricted cash, de-SPAC), a residual above both 0.5% and $0.1M opens a review (starting values).
- D-M04-17 (2026-10-12, review 2.4a): Estimate changes — bands < 10% / 10–25% / ≥ 25% of the denominator, both directions; two prior 10-Ks per company fetched (≤ ~28 requests, skipping ETV and INFQ shell years) for recurrence tests (DS7).
- D-M04-18 (2026-10-12, review 2.5a): Estimate-share denominator — company figures on the amount's own tax basis and period; not meaningful when ≤ 0 or below 1% of revenue; segment share only when segment profit is stored or quoted.
- D-M04-19 (2026-10-12, review 2.6a): Recurring "one-time" charges (outline Red Flag 3) — `special_items`: restructuring, impairment and write-down tags plus FTS5 "non-recurring"/"one-time" wording in ≥ 3 of the last 4 years (starting value); cumulative size vs operating income; the company-stated non-GAAP vs GAAP gap, quoted, never computed (D-M02-29).
- D-M04-20 (2026-10-12, review 2.7a): Stage routing in Round 2 — events, M-score (SGI = 1), misstatement score and revenue gaps are stage-neutral; 3-year CFO/NI < 0.8 warns for mature and decline, a note for introduction, growth and shake-out; accruals vs own history, no warning.
- D-M04-21 (2026-10-12, review 2.8a): Open 4.02 — until the restated filing, every M04 row reading the affected periods (CvD, gate, F/G/Z, `guidance_hit_rate`) is marked "inputs under non-reliance" and warns; adds are not blocked (D16).
- Round 2 suggestions S2.1–S2.11 accepted ("rest ok"; docs/m04_review/R2_brief.md). 2.9 settled by D-M04-11.
- D-M04-22 (2026-10-12, review 3.1a): Issuance measure — log change in basic weighted-average shares, same quarter a year apart, both values from one filing (split-safe); checked against `shares_cover` (D-M04-2); not meaningful across an IPO, de-SPAC or recast.
- D-M04-23 (2026-10-12, review 3.2a): Issuance bands — yearly percentiles of same-filing pairs for filers with public float ≥ $700M, blank checks (SIC 6770) out; top quintile = "extreme" (CY2025 cut +12.1%); 12-month window with the 5-year composite beside it.
- D-M04-24 (2026-10-12, review 3.3a): Shelves and ATMs — filing metadata plus each 424B's fee exhibit (~250 requests one-off); text read only for IPO lock-ups and resale counts. A shelf is capacity, not a raise; resales add no shares.
- D-M04-25 (2026-10-12, review 3.4a): When dilution warns — untagged and `issuance_funded` names: `financing_pressure` warns when issuance is extreme or serial and the gate state is fail or warn (D-M04-13: `issuance_funded` with a passing gate outside the warn band → `m04_dilution` review); `asset_treasury`, `reit` → review; `fund`, `financial` excluded; `spac_shell` not meaningful. One condition alone is information.
- D-M04-26 (2026-10-12, review 3.5a): Serial dilution to survive — the gate condition also holds if the gate failed or warned in any of the 4 quarterly filings before the share jump; cover counts tested too; serial = extreme in ≥ 2 of 3 years or a top-quintile 5-year composite (starting values). Boeing 2024–25 is the regression case.
- D-M04-27 (2026-10-12, review 3.6a): Stage routing in Round 3 — on the owner-confirmed stage; a gate failure warns at every stage; a gate warn warns for mature, shake-out and decline and is an `m04_dilution` review for introduction and growth; under 3 years both readings labelled, uncounted (D-M04-7).
- D-M04-28 (2026-10-12, review 3.7a): Linked causes — only non-cash causes (share-paid acquisition, IPO/de-SPAC recast, split, 3.03 recap) make issuance information; cash raises (424B5, ATM, 3.02 placements) keep the warning while the gate fails or warns, cause shown.
- D-M04-29 (2026-10-12, review 3.8a): Debt against revenue (outline Red Flag 6) — `debt_to_revenue` (total debt ÷ TTM revenue) and net debt ÷ EBITDA as information rows (Round 4 block), against own 3-year range and peer robust z; no vote until Part 8.
- D-M04-30 (2026-10-12, review 3.9a): Cash burn with no share gains (outline Red Flag 1) — a joint warning row: burn (runway warn or fail, or FCF on total capex < 0) together with flat or falling market share (Round 6 test); never a gate input; "missing" where no share data exists.
- Round 3 suggestions S3.1–S3.10 accepted (docs/m04_review/R3_brief.md).
- D-M04-31 (2026-10-12, review 4.1a; amends the D-M04-1 survival gate): Altman Z (manufacturers), Z'' and Ohlson O leave the gate and become a stage-labelled `distress_score` warning; the gate uses liquidity and legal facts only; M01 opens rule-3 adds and rule-7 (D27) strength only on gate pass (pass with warn included).
- D-M04-32 (2026-10-12, review 4.2a; amends the D-M04-1 runway): Runway — burn = OCF − total capex (D-M04-6), the worse of TTM ÷ 4 and the last two quarters; liquidity = cash + confirmed undrawn credit maturing beyond the horizon. Cash burners (incl. `issuance_funded`) fail below 6 quarters and warn below 8; capex-funded names (OCF > 0) warn below 8, go to review below 6, never fail.
- D-M04-33 (2026-10-12, review 4.3a): Maturity wall — debt due within 12 months above liquidity fails every gated name (commercial paper never added twice); 12-month debt + 4 × burn above liquidity warns; the 24-month wall is shown.
- D-M04-34 (2026-10-12, review 4.4a): Going-concern and covenant text — fail on an auditor going-concern paragraph, a management "substantial doubt exists" conclusion, an unwaived covenant breach, forbearance or covenant-driven debt reclassification; alleviated doubt, audit-matter-only mentions, waived or reset covenants → warn + review; hypothetical wording → review only when runway < 8 quarters; `spac_shell` periods excluded; one-off EFTS history pass as baseline.
- D-M04-35 (2026-10-12, review 4.5a): A "not applicable" gate (untagged FF12 group 11, `fund`, `financial`) reads as not-pass for M01 until a sector gate exists; "withheld" maps to incomplete.
- D-M04-36 (2026-10-12, review 4.6a): Input age — older facts labelled "as of <date>"; foreign annual filers use annual burn up to 16 months, then incomplete; domestic filers follow the S1.6 `overdue` rule.
- D-M04-37 (2026-10-12, review 4.7a): 8-K triggers — 1.03 fails and never clears by itself; 2.04 fails until a later clean periodic filing and owner resolution; 3.01 fails on delisting or a missed cure, a cure-period deficiency warns + review; a 3.01 listing transfer is information (S1.11).
- D-M04-38 (2026-10-12, review 4.8a): Capex-funded name in review below 6 quarters — while open, rule-3 adds allowed, rule-7 strength blocked.
- D-M04-39 (2026-10-12, review 4.9a): Massive negative FCF (outline Red Flag 4) — `fcf_burn` information row (TTM FCF ÷ revenue and ÷ liquidity, operating vs capex-funded, `capex_split` context) beside `fcf_growth`; threshold set at Part 8.
- Round 4 suggestions S4.1–S4.13 accepted (docs/m04_review/R4_brief.md); M04 weekly review cap 5 (starting value).
- D-M04-40 (2026-10-12, review 5.2a): R12 trigger — TTM revenue up and gross margin down ≥ 3 pp year over year in 2 straight quarters (reported basis; excluding-stated-items margin beside it); episode closes after 2 non-qualifying quarters; runs at every stage; one `m04_margin_cause` item per episode.
- D-M04-41 (2026-10-12, review 5.3a): Cause naming — code tags cause sentences ("primarily due to", "driven by", …) into classes with an arithmetic check of stated components; owner confirms; Gemini only on request (D28).
- D-M04-42 (2026-10-12, review 5.4a): Unit KPIs, segments, customer axes — Tesla delivery extractor (DS2), EX-99.2 exhibits, RIVN tracked, filing-instance reads into a new `fact_dim` table (~180 backfill requests).
- D-M04-43 (2026-10-12, review 5.5a): Customer signal (D-M04-1 customer row) — engine proposes the stickiness class, owner confirms; data from instance axes, else sentences; only customer-named 8-Ks count; "weakening" needs owner confirmation.
- D-M04-44 (2026-10-12, review 5.6a): Confirmed R12 cause — price, mix or competition → `r12_warning` plus a CvD Q2 "weakening" vote; volume, input cost or FX → watch; one-off, accounting, segment or credits → cleared but fed to Round 2's recurrence count.
- D-M04-45 (2026-10-12, review 5.7a): Round 5 flags that count — confirmed R12 warnings and young-firm per-unit flags count (not while the stage is unconfirmed); flags on unsourced thresholds stay information until Part 8 calibration on ≥ 20 owner-labelled episodes.
- D-M04-46 (2026-10-12, review 5.8a): Stage → flag set — introduction → young set; growth → young set plus the SG&A rule; mature → mature set; decline → mature set, reversion prior unused; confirmed shake-out → all-stage flags only.
- D-M04-47 (2026-10-12, review 5.9a): Burning with falling units (R11, Rivian) — young-firm warning when TTM units fall while FCF (total capex) < 0; feeds the Red Flag 1 row (D-M04-30).
- D-M04-48 (2026-10-12, review 5.10a): Positive margin rows (D-M04-11) get an "excluding stated items and credits" basis beside reported, with the reversion prior shown.
- D-M04-49 (2026-10-12, review 5.11a): Contracted RPO — "weakening" when RPO is below its 3-year minimum for 2 quarters; a break in RPO ÷ revenue alone opens a review.
- D-M04-50 (2026-10-12, review 5.12a): Revenue-at-stake weight — design-in customer vote = min(1, revenue at stake ÷ 0.25) (starting value); contracted 1; transactional 0; missing excluded.
- Round 5 suggestions S5.1–S5.16 accepted (docs/m04_review/R5_brief.md).
- D-M04-51 (2026-10-12, review 6.1a): Calibration test set — the owner blind-labels 24 CvD episodes (15 up to FY2017, 9 from 2018) plus 4 controls; tuning covers only activation, the z cut, the majority rule and the gauge threshold; information rows are reported, not tuned; episode prices per D-M04-72.
- D-M04-52 (2026-10-12, review 6.2a; amends D-M04-1 peer z): Few-peer statistics — robust z on MAD × 1.4826 × the small-sample factor b_n for 5–9 peers (IQR ÷ 1.35 kept for ≥ 10); fixed-gap fallback below 5; drop |z| > 3 once before scoring.
- D-M04-53 (2026-10-12, review 6.3a; amends D-M04-1 health score): F-quality (0–4, extended to 0–5 by D-M04-59) is the only health-score vote (≥ 3 intact, 2 neutral, ≤ 1 weakening); Piotroski F and Mohanram G are shown, not voted.
- D-M04-54 (2026-10-12, review 6.4a; amends D-M04-1 rows): Profile corrections — normalized earnings power on both bases (current revenue and cycle-average revenue); Q2 intensity row uses total capex intensity and the R&D level; trough comparisons use 5 pp turning points, write-down adjusted; ROIC must agree with gross margin for "intact".
- D-M04-55 (2026-10-12, review 6.5a; amends D-M04-1): Activation and zones — CvD is active when TTM revenue falls, gross margin falls ≥ 3 pp, or operating income falls ≥ 25% (also D-M04-67); otherwise state NO_SLOWDOWN. "Shared" needs peers falling too; z zones are open-ended; readings between the cycle and company-specific zones are neutral.
- D-M04-56 (2026-10-12, review 6.6a; amends D-M04-1 "disagree → AMBIGUOUS"): Missing rows leave the denominator; ≥ 2 rows must be present; a question resolves on a 2/3 majority of present weight (customer row weighted per D-M04-50; the R12 vote counts only when it fires); cvd_confidence = the lower of the two questions' winning shares; coverage is shown beside it.
- D-M04-57 (2026-10-12, review 6.7a): Overreaction gauge — gap = 4-quarter price change − change in normalized earnings power on current revenue, same 4 quarters; flagged at ≤ −25 pp (starting value); the cycle-average base shown beside it.
- D-M04-58 (2026-10-12, review 6.8a): How M01 reads CvD — only CYCLICAL_TROUGH with a gate pass adds rule-7 (D27) strength; NO_SLOWDOWN allows tranches; AMBIGUOUS, STUMBLE, CYCLE_PLUS_DAMAGE, STRUCTURAL_DECLINE and overdue block tranches. Recorded in M01 as D-M01-5.
- D-M04-59 (2026-10-12, review 6.9a): CFO > 0 joins F-quality (0–5: ≥ 4 intact, 3 neutral, ≤ 2 weakening).
- D-M04-60 (2026-10-12, review 6.10a): Restatement, `special_items`, `financing_pressure`, `distress_score` and the Red Flag 1 row are shown and reviewed with no D13 weight until ≥ 20 owner-labelled episodes exist (same rule as D-M04-45).
- D-M04-61 (2026-10-12, review 6.11a): Overdue and stale — an overdue filing (S1.6) makes the gate incomplete and raises an exit warning (D16); "stale" (D-M04-1) marks the carried CvD state once a period has ended unfiled, and later tranches wait for the filing.
- D-M04-62 (2026-10-12, review 6.12a): Rule-7 strength does not need the overreaction gauge; the gap is shown ("informs, never overrides").
- D-M04-63 (2026-10-12, review 6.13a): Intel regression expectation — AMBIGUOUS → owner review until the share and moat rows exist; the owner's answer is the expected state.
- D-M04-64 (2026-10-12, review 6.14a): Capex surge into falling revenue — total capex ÷ revenue > 1.5× its own 3-year average while revenue falls → the Q2 capex row reads neutral, with a pointer to M05.
- D-M04-65 (2026-10-12, review 6.15a): Equity point in the health vote — Round 3 measure (D-M04-22, -23), routed by tag then stage (D-M04-27); lost only on extreme or serial issuance (D-M04-26), for `issuance_funded` only when `financing_pressure` warns (D-M04-25); unconfirmed stage → missing.
- D-M04-66 (2026-10-12, review 6.16a): One-time items in normalized earnings power — reported and ex-items both shown (D-M04-48); an item is excluded only if nothing similar occurred in the prior 10 years; repeats feed `special_items` (D-M04-19).
- D-M04-67 (2026-10-12, review 6.17a): Activation on the latest quarter — CvD is also active when the latest quarter's revenue is ≥ 10% below a year earlier (starting value).
- D-M04-68 (2026-10-12, review 6.18a, new): Market share — owner-entered third-party share (grade B) or share computed from a stated industry total (grade A); Q2 "falling" = down ≥ 1 pp over 4 quarters in a flat or growing market; Red Flag 1 "no gains" (D-M04-30) = up < 1 pp (illustrative, set at Part 8); otherwise "missing: no share data".
- Round 6 suggestions accepted as in docs/m04_review/R6_brief.md (incl. S6.15: a Tiingo symbol counts only when its name and dates match the SEC company).
- D-M04-69 (2026-10-12, build B.1a): One `scripts/run_financials.py` with a subcommand per part, `--no-sec`, the lock via `run_script`, and a log of requests, MB and seconds per fetch type.
- D-M04-70 (2026-10-12, build B.2a): The logon refresh runs per-new-filing work only (~350–390 requests a year; heaviest day under a minute); finders run on stored text; backfills are owner-run.
- D-M04-71 (2026-10-12, build B.3a): Review order — survival; CvD AMBIGUOUS and stage changes; events; restatement; dilution; margin, customer, unit KPI; estimate and M-score. Existing hits are baselined except items filed in the last 12 months and a current gate fail or incomplete. The setup batch (15 stages, peer shortlists) is outside the weekly cap of 5 and comes before Part 3.
- D-M04-72 (2026-10-12, build B.4a): Delisted and recycled tickers — a Tiingo symbol is used only when its name and dates match the SEC company (BBBYQ, RADCQ, NVTAQ, SHLDQ, RSH/RSHCQ, FIT, BTUUQ, GPRO); last real trade found first; BTU and CHK checked for splices; J.C. Penney "missing: no prices"; ≤ 34 Tiingo requests.
- D-M04-73 (2026-10-12, build B.6a): Red-flag labels — the owner blind-labels red flags during Parts 3–7 on Round 6's episodes plus GE, Invitae, RadioShack, Sears, Rivian, MSTR, Target, Tesla (controls Lockheed, Alphabet); weights are set at a High-effort review after Part 8b.
- D-M04-74 (2026-10-12, build B.7a; extends D13): `signal` gains `cik` for all modules, in the same migration as `value_text`; the ticker is for display.
- D-M04-75 (2026-10-12, build B.9a): Peer and episode facts — one companyfacts download per company, keep only M04's tags, then drop the cache file.
- D-M04-76 (2026-10-12, closing C.1a; = D-M01-6): First entry (R3, M01 rule 1) — a first entry needs a survival-gate pass (warn included), no overdue filing, and CvD not STRUCTURAL_DECLINE or CYCLE_PLUS_DAMAGE. A company whose gate cannot yet be computed (e.g. SPCX before inputs exist) gets no first entry until it computes.
- D-M04-77 (2026-10-12, closing C.2a): 8-K events (M01 rule 6) — every 8-K event shows at once as an uncapped alert line on the M04 tab and in the end-of-run summary box; only the `m04_event` judgment item counts against the weekly cap (D-M04-71).
- D-M04-78 (2026-10-12, closing C.3a): "Total capex" for the gate, FCF and Q2 rows is the own-history series of D-M04-3 (longest consistent tag); M02's company-definition OCF ÷ capex is shown beside it, labelled "company definition".
- D-M04-79 (2026-10-12, closing C.4a; extends D-M04-10): Guidance rows — a floor is scored as a low end; ceilings and direction-only rows are unscored (as M02 ranks them, D-M02-28); rows with an open `guidance_implausible` or `guidance_conflict` item stay unscored until resolved; owner-corrected rows win (D-M02-24); an outcome takes its row's grade (call = B, D-M02-21).
- D-M04-80 (2026-10-12, closing C.5a): Tier scope — full M04 for core and promoted names; tracked names get facts-only rows (gate numbers, CvD numeric rows), text rows read "missing: tracked tier, no documents", no peer fetches and no review items.
- D-M04-81 (2026-10-12, closing C.6a): RIVN enters as a promoted name through the UI (D-M02-11); `config/watchlist.toml` stays the owner's.
- D-M04-82 (2026-10-12, closing C.7a): Daily prices (Tiingo) carry evidence grade A in every module (exchange data), as M01 already does.
- D-M04-83 (2026-10-12, closing C.8a): Cycle-average window for normalized earnings power — trough to trough using the 5 pp turning points (D-M04-54); with no completed cycle in XBRL, the longest available history, labelled. Needed before the M06 review.
- D-M04-84 (2026-10-12, Part 1b live check 1, owner; refines D-M04-10, -79): Direction-aware guidance scoring — revenue, margin, EPS and income metrics (and capex) miss when below the low end (or floor); cost metrics (operating expenses, total expenses, cost of revenue) miss when above the high end (a ceiling is their high end; a floor on a cost is unscored); tax rate and other income are unscored, "not a performance target", and still shown (NVIDIA's and Meta's tax-rate rows). A capex guide is scored only when M02's recipe for the company is exact; an approximate recipe or an unmapped clause reads "unscored: capex recipe approximate (<clause>)" (Microsoft FY2026 Q4: guide ≥ $40B, PP&E-only actual $35.8B).
- D-M04-85 (2026-10-12, Part 1b live check 1, owner; refines D-M04-10 "removed" and M01 rule 4): Only core families count as removed and feed `guidance_removed` / M01 rule 4: revenue, gross margin, EPS, operating income, net income, capex, FCF. Other families' removals (operating expenses, tax rate, other income …) are stored and shown as "dropped (information)" (outcome `dropped`, migration 0031), never in the signal.
- D-M04-86 (2026-10-13, owner at the wave B mock-up approval; Part 4a): Manual credit-line entry — the gate panel's "Add confirmed credit line" (facility, undrawn amount, maturity, the balance sheet it was stated for, source sentence or URL) writes `credit_line` with the owner as confirmer (origin `owner`, status `confirmed`, grade A with a filing source, else B) and the gate recomputes. A line counts when confirmed, stated for the gate's balance sheet (within 45 days before it) and maturing more than 12 months after it; a newer 10-Q or 10-K needs a new confirmation (pack S4.2). Part 4b's finder proposes lines into the same table (origin `finder`, status `proposed`, verified passage, `m04_credit_line` item). Rows are withdrawn, never deleted.
- D-M04-87 (2026-10-13, Part 4a build; S4.4, D-M04-31): `distress_score` warns on the Z (SIC 2000–3999) or Z'' zone only; for a manufacturer Z'' is shown beside Z; Ohlson O (Model 1, assets in dollars, GNP deflator 1968 = 100 for the prior year, OCF as the FUTL proxy) is information beside its 0.038 cut-off, missing for years whose deflator is not in the table (2020, 2021, 2025 read by the review). Market value = class-summed cover count × the latest close (within 5 days), its date in the method; the row is updated in place by the logon pass.
- D-M04-88 (2026-10-13, Part 4a build; D-M04-71): Part 4a items open on a turn — `m04_gate_fail` when the gate turns fail or incomplete (a first run that finds one queues it), `m04_runway` when a capex-funded runway turns below 6 quarters, `m04_score_gap` when the score turns distress while the gate passes — remembered in `refresh_state` (`m04_gate:<cik>`), so a state that holds opens nothing new; an unanswered item whose condition ends is withdrawn. `m04_gate_input` is one item per company and input (capex, cash, OCF), withdrawn when the input appears; Map tag stores an owner tag for the input, Not reported keeps the labelled fallback.
- D-M04-89 (2026-10-13, Part 4a build; D-M04-37, -21): The gate's 8-K triggers are items 1.03, 2.04 and 3.01 in their Part 3 state (fail or warn); other open events (4.01, 2.06, NT, 1.02) are listed beside the gate and are not triggers; an open 4.02 marks the inputs "under non-reliance" and warns. Tagged undrawn capacity without a maturity is never counted as liquidity.
- D-M04-90 (2026-10-13, Part 6 build; refines D-M04-14, S2.3, S2.4): Earnings-quality inputs are the values as first reported in each fiscal year's own periodic report (tag and accession kept). Optional balance-sheet lines (short- and long-term investments, current debt, preferred stock, long-term debt, inventory): no tag in either year → none on the balance sheet, named; tagged for the prior year only → none now when the current report still tags the prior year (the line ended), else a suspected tag switch → incomplete (NVIDIA FY2026 short-term investments); tagged for the current year only → a new line, prior none, named. M-score: a missing input makes it incomplete before the gross-margin test; ACCR on income from continuing operations where tagged; substitutions (D&A for depreciation, S&M + G&A for SG&A, derived total liabilities, `LongTermDebt` for the noncurrent tag) are named in the method. `issue` = proceeds from common stock, stock plans or long-term debt above 0 in the year; none of the tags → unknown → missing. Amended at live check 1 (2026-10-13): `issue` reads M02's `debt_raised` / `equity_issued` roles (built-ins and the owner's `fin_tag_map`, D-M02-31) plus the stock-plan, debt and IFRS proceeds tags; 1 when any is > 0 (tag named), 0 when none is for the year but one is tagged in another year, else unknown. SG&A = SG&A, else S&M or marketing + G&A, else G&A alone ("G&A only"); cost of revenue = the tag, else revenue − gross profit, else the `CostOf…` lines only when they and the other tagged operating lines equal the operating-cost total within 0.5%; cash falls back as the gate's (D-M04-32); receivables add the IFRS trade-receivable variants; long-term investments include the noncurrent marketable-securities tags (owner).
- D-M04-91 (2026-10-13, Part 6 build; refines D-M04-20, S2.1, S2.2): `eq_cash` = 3-year CFO ÷ 3-year net income, each year on the operating basis when its identified non-operating items (securities and digital-asset fair-value changes after 21% / 35% tax, the valuation-allowance change as reported) exceed 25%† of |NI|, else reported (Tesla 2023 → 9,035; Tesla's 3-year ratio 1.50 instead of the reported 1.24). States: ok (≥ 0.8), warn (confirmed mature or decline), note (confirmed introduction, growth, shake-out), warn_or_note (stage unconfirmed; not counted), not_meaningful. Accruals compare with the company's own 5 prior years (above / within / below the range; peer z not built). Contract-asset and deferred-revenue readings are fiscal years (quarters later); any tag change between the two values of a reading reads "definition changed" and is not scored. Amended at live check 1: "the last 2 readings" are consecutive fiscal years ending at the latest fiscal year (older readings are shown, not counted); a reading in an acquisition year (Part 2's test: cash for businesses or the goodwill rise ≥ 10%† of revenue) is shown with the note and not counted.
- D-M04-92 (2026-10-13, Part 6 build; refines D-M04-17, -18, S2.7): Estimate finder — FTS5 on estimate wording in the current and two prior annual reports; a sentence counts when the wording is in it or in the 400 characters before it, it states a $ amount and what it moved, and it has no may / could / might / if; one amount per sentence (after-tax, then pre-tax, then an expense line with the opposite sign; the others listed); the year named in the sentence, else the report's fiscal year; the denominator as known on the report's filing date; rows keyed by accession and sentence offset (filing version). Recurrence = the largest change of each of the 3 disclosures has the same sign. Catch-up revenue (`…SatisfiedInPreviousPeriod`) is revenue, shown against own history with a same-sign-3-years flag, never a share. Amended at live check 1 (replaces the 400-character look-back): the wording must be in the sentence with the amount, or in the sentence directly before one that refers to "this change" / "such adjustments" (or that a line break cut); variance wording ("compared with", "year over year", "or N%") passes only when the sentence itself names an estimate change; table rows take the first column for the report's year with parentheses negative (wording within the 3 sentences before; per-share rows skipped); one row per filing, fiscal year and amount; "…, respectively" lists map amounts to years; a reference company's reports can be named (GE FY2016 and FY2017).
- D-M04-93 (2026-10-13, Part 6 build; refines D-M04-19, D-M04-71): `special_items` counts a fiscal year (of the last 4) with a non-zero restructuring, asset-impairment, goodwill-impairment or inventory write-down tag, or "non-recurring" / "one-time" (hyphenated) wording in that year's stored annual report; years without stored text count on tags only and say so; the non-GAAP sentence is quoted from the newest stored EX-99.1. Review kinds: `m04_mscore` per fiscal year (last 3) whose SGI = 1 M is above −1.78 — actions Explained / Look closer, no data change; `m04_estimate` per sentence at ≥ 10% — Explained / Concern, stored on the `estimate_change` row and never re-queued; both group 7; first scan a baseline (12-month exception); a finding that no longer holds is withdrawn. Live check 1: the per-year test is one function (`special.qualifies`) so the pending owner answer on wording-only years changes one place.
- Build-part suggestions SB.1–SB.18 accepted (docs/m04_review/BP_brief.md); B.5, B.8 settled by D-M04-11, D-M04-2.

## Decisions carried from DESIGN.md
- Red flags are stage-aware; ambiguous stage → review queue. (R2; stage rule D-M04-7, confirmation D-M04-12)
- Rivian = unit-economics case; GE = earnings-quality case. (R11)
- Revenue up + margins collapsing → identify the cause. (R12)
- Capex split: disclosed → project-level → Greenwald (default) → D&A; every value method-tagged. (A2; default changed to depreciation by D-M04-6)

## Open questions
Design points the review left open. The doc follows the reading shown until the owner answers; answers become D-M04-76 onward. Build-level points (R1 depth, `evidence_grade` on missing rows, label-file location, RIVN tier, recounts) are in M04_BUILD_LOG.md "Open points for the build".
- **Liquidity-only and trust-only gates:** named for `asset_treasury`, `reit` and `spac_shell` (D-M04-8) but not defined. Does liquidity-only use only the runway and the maturity wall, and do the text and 8-K triggers apply to either? *Part 4a builds the conservative reading (Survival gate, "Built"): liquidity-only tests the 12-month wall (fail and warn), 8-K triggers and filing status, the runway shown only; trust only reads the trust account (pass when stated) plus 8-K triggers and filing status. Open for the owner.*
- **D13 weight of "burning with falling units" (D-M04-47):** a young-firm flag that counts now (D-M04-45), or part of the Red Flag 1 row, unweighted until ≥ 20 labels (D-M04-60)? Shown as "disputed".
- **Unsourced thresholds that count now:** D-M04-45 counts R12 (3 pp) and the young per-unit flags although their thresholds are unsourced; the other unsourced Round 5 thresholds (inventory 15 pp, credit share 50%, production gap 10%, SG&A 4 quarters) stay information until calibration. Confirm.
- **CYCLE_PLUS_DAMAGE and M01 rule 4 — closed:** an exit warning. M01 rule 4 (owner-reviewed 2026-10-07) already lists CvD moving to CYCLE_PLUS_DAMAGE or STRUCTURAL_DECLINE, and the pack's M01 table accepted through S6.14 gives "Yes"; the grid's "review" is the `m04_cvd` item (How M01 reads M04).
- **Cycle-average window for NEP (D-M04-54, S6.6):** which years make up the cycle; are they tied to the 5 pp turning points?
- **Evidence grade for prices:** D14 and D-M04-9 grade filings, transcripts, third-party data and owner entries only. The doc labels Tiingo closes "market data".
- **Review queue:** Round 5's per-kind caps (`m04_customer` 3 a week, `m04_unit_kpi` 2 a week) read as superseded by D-M04-71's single cap of 5; `m04_gate_fail` also opens on a gate turning incomplete (D-M04-71); the capex-funded runway review (D-M04-38) has no kind in any round and is named `m04_runway` here; stickiness-class proposals (~15 at first run, D-M04-43) are treated as setup items outside the cap. Confirm.
- **Foreign filers' 6-K events:** 6-Ks carry no item codes, so a default or delisting notice has no detector. Known omission; no decision closes it.
- **Proposed names:** signal names starred in "Signals out" and the `m04_runway` kind were proposed at the redraft; confirm at build. (Part 6 confirmed `eq_accruals` and `mscore_sgi1`.)
