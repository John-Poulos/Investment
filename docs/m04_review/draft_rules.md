# M04 — Financials & red flags: rules (redraft, part 1)

Draft for the redrafted M04_FINANCIALS.md. Binding source: D-M04-1…75; suggestion IDs (S1.x–S6.x, SB.x) point to the round briefs. Thresholds marked † are starting values, calibrated at Part 8b (D-M04-51) or, for red flags, at the High review after 8b (D-M04-73). Missing data stays missing (`method` = "missing: <reason>"), never zero (D-M04-9). Outputs are research signals; the owner decides (D8, D16).

## Purpose
Judge financial health and earnings quality, flag the outline's red flags by life-cycle stage (R2), and classify a slowdown as cycle or decline (CvD) for M01's entry and exit rules (D27).

## Inputs
| Data | Source | Grade | Refresh |
|---|---|---|---|
| Point-in-time facts: `facts_as_of()` (periodic forms only, tag priority after time, de-SPAC boundary); every value carries tag and accession (S1.1, S1.4) | `fact` (companyfacts) | A | Logon refresh, per new filing (D-M04-70) |
| Share series `shares_period_end`, `shares_cover`, `shares_basic_wavg`, `shares_diluted_wavg`, `sbc`; multi-class cover from R1 pages; implied float (D-M04-2) | `fact`; R1 pages | A | Per new filing; multi-class R1 ~1 per filing |
| Capex: company definition for display, longest consistent tag for own history, PP&E tag only for peers (D-M04-3); `capex_split` ladder (D-M04-6) | `config/capex_definitions.toml`; `fact`; NVDA instances | A | Per new filing |
| Peers: 4-digit SIC proposals from a ranked shortlist, owner-confirmed `peer_group`; non-SEC peers "missing" (D-M04-4); periods TTM ±45 d, quarters/instants ±40 d† (D-M04-5); peer facts trimmed to M04 tags (D-M04-75) | submissions, browse-by-SIC, companyfacts | A | Peer companyfacts on a new peer filing |
| Life-cycle stage, owner-confirmed (D-M04-7, -12) | Cash-flow totals in `fact`; owner | A (owner confirmation) | Per new 10-K |
| Model tags (D-M04-8) | `config/company_models.toml`, hand-edited | Owner | On edit |
| Guidance record, `guidance_hit_rate` (D-M04-10) | Guidance ledger (`guidance/`), first-filed facts | A; B if from a transcript | Per earnings release |
| 8-K items 1.01–1.03, 2.01, 2.04, 3.01–3.03, 4.01, 4.02, 5.06 (D-M04-15, -28, -37) | `event` | A | Logon refresh |
| Filing text: going concern, covenants, restatement wording, causes, estimates, credit lines, overhang, ratings (D-M04-15, -19, -34, -41) | corpus (FTS5), EFTS one-off history | A (verified quote) | Finders run on stored text |
| Dimensional facts: segments, customers, missing 10-Q lines (D-M04-42) | Filing instances → `fact_dim` | A | One instance per new 10-K/10-Q |
| Unit KPIs, credits (D-M04-42) | `unit_metric`: Tesla DS2, EX-99.2, 10-K sentences | A | Per release |
| 424B fee exhibits, shelves (D-M04-24) | Filing index, fee exhibit | A | Per new 424B |
| Issuance bands (D-M04-23) | CY frames (float ≥ $700M, SIC 6770 out) | A | Once a year |
| Daily closes; delisted symbols only on name and date match (D-M04-72, S6.15) | Tiingo | Market data (see Open questions) | Nightly prices |
| Owner entries: market share (D-M04-68), undrawn credit, stickiness class (D-M04-43), peer and stage confirmations | Setup page, review items | B without a filing source; A with one (D-M04-9) | On entry |

## Company profile

### Life-cycle stage (R2)
- **Computed:** Dickinson signs of (CFO, core investing, financing); core investing = capex + acquisitions − asset and business sale proceeds. A stage holds when 2 of the last 3 fiscal years agree (D-M04-7).
- **Review (`m04_stage`)** when no stage holds 2 of 3, the held stage is shake-out, the stage conflicts with 3-year revenue CAGR (introduction/growth with CAGR < 0; mature/decline with CAGR > 20%†), or fewer than 3 fiscal years exist (D-M04-7).
- **Confirmation:** the owner confirms each company's first stage once (setup batch, 15), then computed changes and ambiguous cases, about 4–5 a year (D-M04-12). Owner override.
- **Until confirmed:** the last confirmed stage routes. With none, the young and the mature flag sets are both computed, labelled "stage unconfirmed" and not counted in D13 (D-M04-7).
- Stage routes flags only. R12, inventory-vs-sales and the survival gate run at every stage (D-M04-7).

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

## Cycle vs. Decline (CvD) profile
Approved structure of D-M04-1, amended. A changed cell carries its D-M04-n. Units: pp = percentage points.

### Activation
CvD runs when the latest filed quarter shows any of: TTM revenue down year over year; TTM gross margin down ≥ 3 pp†; TTM operating income down ≥ 25%† (D-M04-55); the latest quarter's revenue ≥ 10%† below a year earlier (D-M04-67). It switches off after 2 straight quarters with none of these (S6.9). Otherwise `cvd_state` = NO_SLOWDOWN (D-M04-55).

### Peer statistics
- Robust z = (company − peer median) ÷ scale. Scale: IQR ÷ 1.35 for ≥ 10 peers; MAD × 1.4826 × b_n for 5–9 peers; fewer than 5 → fixed-gap fallback, z information only. Drop any peer with |z| > 3 once and recompute (D-M04-52). Method, n and b_n stored; the gap in pp always shown (S6.2).
- A peer period counts only inside the offset tolerance (D-M04-5) and from its filing date; otherwise "awaiting peer filing" or "no comparable period" (missing), which counts toward the < 5 fallback (S6.1). 2-quarter persistence kept.

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
| Guidance record (D-M04-10) | Hit rate steady | 2† misses in the last 4 guided quarters, or a quiet removal | Point and "approximately" guides unscored; release-silent → "missing (DS1)" | `guidance_hit_rate` |
| Health score (D-M04-53, -59, -65) | F-quality ≥ 4 of 5 | F-quality ≤ 2 | 3 → neutral; Piotroski F and Mohanram G shown, not voted | XBRL |
| R12 cause (new vote, D-M04-44) | — | Owner-confirmed price, mix or competition cause | Present only when it fires (D-M04-56) | R12 episode |

- **F-quality** (0–5): accruals, leverage, liquidity, equity, CFO > 0 (D-M04-53, -59). The equity point uses the Round 3 measure routed by tag then stage; it is lost only on extreme or serial issuance, and for `issuance_funded` only when `financing_pressure` warns; unconfirmed stage → missing (D-M04-65).
- **Customer weight:** design-in vote = min(1, revenue at stake ÷ 0.25†); contracted 1; transactional 0; missing excluded (D-M04-50).
- **Open 4.02:** rows reading the affected periods are marked "inputs under non-reliance" and warn; adds are not blocked (D-M04-21).

### Classification
Each row returns a side, neutral (present, no side), or missing with its reason; missing rows leave the denominator. A question needs ≥ 2 present rows and one side holding ≥ 2/3† of present weight; otherwise AMBIGUOUS → `m04_cvd` review, and the owner's answer becomes the state (D-M04-56, D-M04-63).

| | Franchise intact | Franchise weakening |
|---|---|---|
| Shared slump | CYCLICAL_TROUGH → adds allowed on M01 trigger | CYCLE_PLUS_DAMAGE → warning; review |
| Company-specific | STUMBLE → review | STRUCTURAL_DECLINE → no adds; exit warning |
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

### How M01 reads M04 (D27; D-M04-58 = D-M01-5)
| M04 output | Rule 3: later tranches | Rule 7: strength beyond 2σ | Rule 4: exit warning |
|---|---|---|---|
| CYCLICAL_TROUGH, gate pass or warn | Allowed | Yes (gauge not required, D-M04-62) | — |
| NO_SLOWDOWN, gate pass or warn | Allowed | No | — |
| AMBIGUOUS, STUMBLE | Blocked until the owner resolves | No | — |
| CYCLE_PLUS_DAMAGE | Blocked | No | Warning |
| STRUCTURAL_DECLINE | Blocked | No | Yes |
| Stale (carried state) | First tranche may use it; later tranches wait (D-M04-61) | As the carried state | As the carried state |
| Overdue | Blocked | No | Yes (D-M04-61) |
| Gate fail | Blocked | No | Warning |
| Gate incomplete or not applicable | Blocked; missing inputs listed (D-M04-35) | No | — |
| Capex-funded review open (< 6 quarters) | Allowed | No (D-M04-38) | — |
| Red-flag warnings (`distress_score`, `financing_pressure`, non-reliance, others) | Shown; never block (D16, D-M04-21) | No effect | Listed |

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

### Dilution and financing (outline Red Flags 2, 3 SBC)
| Flag | Trigger | Routing | Output | D13 |
|---|---|---|---|---|
| `net_issuance_yoy` | Log change in basic weighted shares, same quarter a year apart, one filing; cover check (D-M04-22) | Not meaningful across IPO, de-SPAC, recast | Value | info |
| `issuance_pct` | Yearly percentile, float ≥ $700M, SIC 6770 out; top quintile = extreme (D-M04-23); serial = extreme in ≥ 2† of 3 years or a top-quintile 5-year composite (D-M04-26) | All | Band label | info |
| `financing_pressure` | Extreme or serial issuance **and** gate fail or warn now or in any of the 4 quarterly filings before the jump; cover counts tested too (D-M04-25, -26) | Gate fail → warn at every stage; gate warn → warn for mature, shake-out, decline, `m04_dilution` review for introduction, growth (D-M04-27). `issuance_funded` passing outside the warn band, `asset_treasury`, `reit` → review; `fund`, `financial` excluded; `spac_shell` not meaningful (D-M04-13, -25) | Warning. Non-cash cause (share-paid acquisition, IPO/de-SPAC recast, split, 3.03) → information; cash raises keep the warning, cause shown (D-M04-28). One condition alone → information | ≥ 20 |
| Shelves, ATMs, 424Bs | Fee-exhibit amounts; a shelf is capacity, resales add no shares (D-M04-24) | All | Information | never |
| Overhang | Convertibles, warrants, mandatory convertibles from verified text (S3.6) | All | `m04_overhang` review; information | never |
| SBC block, rating actions | SBC ÷ revenue and ÷ OCF, buyback offset (S3.4); actual or review rating sentences (S3.7) | All | Information; `m04_rating` review | never |

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

### Customers and RPO (D-M04-1 customer row)
| Item | Rule | Output | D13 |
|---|---|---|---|
| Stickiness class | Engine proposes (contracted: RPO ÷ revenue ≥ 0.5†; design-in: a ≥ 10% customer or an M02 link, SIC 3570–3679; else transactional); owner confirms (D-M04-43, S5.13) | Setup / `m04_customer` | — |
| Design-in loss signal | Agreement ended (customer-named 8-K 1.01/1.02; 1.02 co-filed with 2.03 = financing unless a customer is named); share below own 3-year minimum while revenue is flat or down; replacement supplier named | `m04_customer` review; "weakening" only after owner confirmation (D-M04-43) | via CvD Q2 |
| Contracted RPO | Below its 3-year minimum for 2 quarters → weakening; an RPO ÷ revenue break alone → review (D-M04-49) | Q2 vote | via CvD Q2 |
| Weight | min(1, at stake ÷ 0.25†); contracted 1; transactional 0; missing excluded (D-M04-50) | `customer_at_stake`, `customer_hhi` shown | info |

### Core trend information rows (outline "Analyze the financials" 1–4)
`rev_yoy`, `rev_cagr3`, `fcf_growth` (on total capex and on owner earnings = OCF − maintenance capex − SBC), `gm_trend_pp`, `opex_vs_sales`: each against own history and as peer robust z; near-zero bases → not meaningful (S2.1); no vote in CvD or confluence until Part 8 (D-M04-6, -11).

## Signals out
Every row: `cik` (key; ticker for display, D-M04-74), one row per timeframe, `value` for numbers, `value_text` for states with `value` NULL, missing = both empty and `method` = "missing: <reason>", `evidence_grade` = weakest deciding input, `source_ref` = newest accession "+N", full inputs in `method` (D-M04-9). ✓ = may carry weight once D13 weights exist, subject to the red-flag D13 column; info = weight 0. One computation serves all timeframes; profiles differ only in weights (S1.5). * = name proposed at the redraft, confirmed at build (Open questions).

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
| `guidance_hit_rate` | %; n in `method` | Q2 guidance row | ✓ | ✓ | info |
| `guidance_removed` | text: removed / expired | Quiet removal event (S1.7) | info | info | info |
| `customer_signal` | text: intact / weakening / info | Q2 customer row | ✓ | ✓ | info |
| `customer_at_stake`, `customer_hhi` | share; index | Disclosed customer exposure | info | info | info |
| `lifecycle_stage` | text: stage, "unconfirmed" | Routing only | info | info | info |
| `filing_status` | text: current / stale / overdue; days in `method` | Filing age | ✓ | ✓ | ✓ |
| `survival_gate` | text: pass / warn / fail / incomplete / not_applicable | Gate verdict; trigger or missing inputs in `method` | ✓ | ✓ | ✓ |
| `runway_q` | quarters, or text "self-funding"; tier in `method` | Runway at D-M04-32 burn | ✓ | ✓ | info |
| `maturity_wall` | ratio | (12-month debt + 4 × burn) ÷ liquidity | ✓ | ✓ | info |
| `gc_language`, `covenant_status` | text class + quote | Latest text class | ✓ | ✓ | ✓ |
| `distress_score` | float; variant in `method` | Z, Z'', O warning | ✓ | ✓ | info |
| `eq_cash`, `eq_accruals`* | ratio; text not_meaningful | Cash conversion, accruals | ✓ | ✓ | info |
| `contract_asset_gap`, `deferred_rev_gap` | pp; text flag | GE pattern | ✓ | ✓ | info |
| `mscore`, `mscore_sgi1`*, `misstate_f` | float; band in text | Screens | info | info | info |
| `restatement` | text: 4.02 / dei / little_r / escalated | Error event | ✓ | ✓ | ✓ |
| `non_reliance`* | text | Open 4.02 mark | ✓ | ✓ | ✓ |
| `restate_delta` | %; text label | Walk step | ✓ | ✓ | info |
| `estimate_share` | %; text band | Profit from estimate changes | ✓ | ✓ | info |
| `special_items` | ratio to operating income; text flag | Recurring "one-time" charges | ✓ | ✓ | info |
| `net_issuance_yoy` | log change | Issuance | ✓ | ✓ | info |
| `issuance_pct` | 0–100; band in text | Percentile | ✓ | ✓ | info |
| `composite_issuance_5y`, `sbc_offset`, `financing_capacity`* | log; ratio; $ | Context | info | info | info |
| `overhang_gross_pct`, `overhang_net_pct` | % of basic shares | Overhang | ✓ | ✓ | info |
| `financing_pressure` | text: warn / review / info / not_meaningful | Dilution to survive | ✓ | ✓ | ✓ |
| `burn_no_share_gain`* | text: warn | Red Flag 1 row | ✓ | ✓ | info |
| `negative_equity`* | text: warn / note | S4.8 | ✓ | ✓ | info |
| `fcf_burn`, `debt_to_revenue`, `net_debt_ebitda`* | ratio | Information rows | info | info | info |
| `r12_episode` | text: open / closed | R12 trigger | ✓ | ✓ | info |
| `margin_cause` | text class; stated $M in `method` | Confirmed cause | ✓ | ✓ | info |
| `r12_warning` | text: warn / watch / cleared | R12 outcome | ✓ | ✓ | info |
| `gm_delta_pp`, `gm_delta_pp_ex_items`, `inventory_sales_gap` | pp | Margin and inventory | ✓ | ✓ | info |
| `unit_gp`, `unit_gp_ex_credits`, `unit_gp_trend`, `unit_cost_vs_cumulative`, `rev_per_unit_vs_cost`, `units_falling_burn`* | $ per unit; text flag | Young unit economics | ✓ | info | info |
| `production_gap`, `credit_share_of_gp`, `sga_vs_revenue` | %; ratio; text flag | Young / growth flags | ✓ | ✓ | info |
| `rev_yoy`, `rev_cagr3`, `fcf_growth`, `fcf_growth_oe`*, `gm_trend_pp`, `opex_vs_sales` | % / pp; peer z in `method` | Core trends | info | info | info |
| `capex_maint`, `capex_growth`, `owner_earnings`* | $; method tag | `capex_split` context | info | info | info |

## Review queue (D8)
- **Order** (D-M04-71): 1 survival · 2 CvD AMBIGUOUS and stage changes · 3 events · 4 restatement · 5 dilution · 6 margin, customer, unit KPI · 7 estimate and M-score.
- **Cap:** 5 judgment items a week across M04† (S4.8); overflow listed on the M04 tab, flushed by order, oldest first. Gate fails are alerts and operational items are uncapped.
- **Baselines:** existing hits are baselined except items filed in the last 12 months and a current gate fail or incomplete (D-M04-71); EFTS history is shown, never queued (D-M04-34).
- **Setup batch** (stages, peer shortlists, credit lines, gate inputs) is outside the cap and comes before Part 3 (D-M04-71).

| Kind | Opens on | First run | Steady state |
|---|---|---|---|
| `m04_gate_fail` (alert) | Gate turns fail or incomplete (D-M04-71); fail-class text | 0 | Rare |
| `m04_gc_text` | Alleviated, audit-matter, IFRS uncertainty; hypothetical when runway < 8 | History baseline only | < 1 a quarter |
| `m04_covenant` | Waived or reset covenant; current-debt jump above roll-down (sub-class `m04_current_jump`) | Baseline | < 1 a month |
| `m04_runway`* | Capex-funded runway < 6 quarters (D-M04-38) | 0–1 | Rare |
| `m04_score_gap` | `distress_score` in distress while the gate passes | 0–1 (BA Z 1.53) | Rare |
| `m04_credit_line` (operational) | Text-found undrawn credit to confirm (runway < 12 or capex-funded warn) | ~2 | Per 10-Q for those names |
| `m04_gate_input` (operational) | Tag to map | 1 (INFQ) | Rare |
| `m04_cvd` | CvD AMBIGUOUS | Set at Part 8a | ~2 a year |
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
