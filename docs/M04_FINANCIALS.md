# M04 — Financials & red flags

Status: CvD profile approved; design review in progress (Rounds 1–5 done) · Updated: 2026-10-12 · Outline headings: Analyze the financials; Financial red flags · Depends on: M00 (SEC data), M02 (peer data), M06, M11 (R19 ledger) · Sources: S02–S04, S13, S20, S25, S32–S37, S43–S45

## Purpose
Judge financial health and earnings quality, and classify a slowdown as a cyclical trough or a structural decline (CvD) for M01's entry and exit rules.

## Decisions carried from DESIGN.md
- Red flags are stage-aware; ambiguous stage → review queue. (R2; stage rule D-M04-7, confirmation D-M04-12)
- Rivian = unit-economics case; GE = earnings-quality case. (R11)
- Revenue up + margins collapsing → identify the cause. (R12)
- Capex split: disclosed → project-level → Greenwald (default) → D&A; every value method-tagged. (A2; default changed to depreciation by D-M04-6)

## Cycle vs. Decline (CvD) profile
Thresholds are starting values; calibrate by backtest. Indicators that disagree within a question → AMBIGUOUS → review queue (D8).
Units: pp = percentage points. Peer z = (company value − peer median) ÷ (peer IQR ÷ 1.35), a robust z-score.

### Q1 — Is the slump shared?
| Indicator | Shared (cycle) | Company-specific | Free source |
|---|---|---|---|
| Revenue growth vs peers (TTM YoY) | Peer median < 0 and company within the pack (−1 < z < 1) | z ≤ −1.5 for 2 straight quarters while peer median ≥ 0 | Frames API + SIC peers (R24); peer IR for non-SEC peers |
| Fallback when < 5 peers | Gap within 10 pp of peer median | Gap ≥ 10 pp below while peers grow | Same; low confidence |
| Industry pricing / volume | Falling industry-wide | Stable or rising | Industry releases (verify at M02); trade press (B) |
| Inventory days | Rising across peers | Rising only here | XBRL |
| Supply response | Peers cutting output/capex together | Peers expanding | Filings, calls (R19) |
| Cycle history | Prior downturns of similar depth recovered | First deep decline | 10+ yrs of filings |

### Q2 — Is the franchise intact?
| Indicator | Intact | Weakening | Free source |
|---|---|---|---|
| Market share | Stable or rising | Falling in a flat or growing market | Segment revenue vs industry totals; third-party share (B) |
| Gross margin gap to peer median (pp of margin) | Change ≥ −3 pp over 4 qtrs | Change < −5 pp | XBRL |
| Trough vs prior trough (GM, ROIC) | Similar or higher low | Lower lows and lower highs over 2 cycles | XBRL history |
| R&D and capex intensity | Held near own 3-yr avg and peers | Cut >20% while peers hold | XBRL |
| Moat (M06), challengers (R21) | Unchanged; no challenger qualified | Challenger qualified at a major customer | M06 |
| Customer base (by stickiness class, weighted by revenue at stake) | Concentration, RPO/backlog and customer events within own historical range | Design-in: loss of a major customer or socket. Contracted: retention/RPO below own range. Transactional: low weight | 10-K/10-Q notes, RPO (XBRL), 8-K Item 1.01, customers' results and capex guidance (M02) |
| Guidance record (R19) | Hit rate steady | Repeated misses, quiet target removals | R19 ledger |
| Health score | F-score (value/cyclical) or G-score (growth) steady | Low or falling (initial F ≤ 3, G ≤ 2) | XBRL + peer medians |

Stickiness classes (owner sets per company; engine proposes): contracted/recurring · design-in/qualified · transactional. No universal customer-loss threshold was found in research; the ≥10% line is a disclosure rule, not a significance test.

### Survival gate (overrides the grid)
Altman Z in the distress zone (original Z for manufacturers, Z'' otherwise; not for financials), or runway (cash + undrawn credit ÷ quarterly burn) < 6 quarters, or next-12-month debt maturities > liquidity → no adds; warning.

### Classification
| | Franchise intact | Franchise weakening |
|---|---|---|
| Shared slump | CYCLICAL_TROUGH → adds allowed on M01 trigger | CYCLE_PLUS_DAMAGE → warning; review |
| Company-specific | STUMBLE → review | STRUCTURAL_DECLINE → no adds; exit warning |

### Overreaction gauge (informs, never overrides)
Price drawdown vs drop in normalized earnings power (cycle-average operating margin × current revenue). CYCLICAL_TROUGH + a large gap = the owner's target setup.

### Regression test cases
- MU 2022–23: industry-wide memory bust, coordinated supply cuts → expect CYCLICAL_TROUGH.
- INTC 2022–25: industry-wide PC slump, but share kept falling into a growing server market → expect CYCLE_PLUS_DAMAGE drifting to STRUCTURAL_DECLINE.
- Invitae 2022–23 (R12): self-inflicted burn → survival gate fails.

## Signals out
| Signal | Type / range | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| cvd_state | enum | Cycle vs decline class | ✓ | ✓ | info |
| cvd_confidence | 0–1 | Share of indicators agreeing | ✓ | ✓ | info |
| survival_gate | pass/fail | Balance-sheet survival | ✓ | ✓ | ✓ |
| overreaction_gap | % | Price drop minus normalized-earnings drop | ✓ | ✓ | info |
| f_score, g_score, z_score | int, int, float | Component health scores | ✓ | ✓ | info |

## Failure modes
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Peer group | Wrong peers fake a shared or company-specific reading; key peers may not file with the SEC (e.g. SK hynix, Samsung) | Owner-curated peers (R24); industry series as fallback; flag missing peers |
| Peer z-score | Unstable with few peers or a one-off quarter | < 5 peers → fixed-gap fallback, low confidence; 2-quarter persistence |
| ≥10% customer list | A customer dropping off may have shrunk below the line, not left | Check revenue-share trend and filings/press before calling a loss |
| Quarterly lag | Price trigger fires before the quarter that confirms the state | Use last known state marked stale; later tranches wait for next filing |
| F-score | Tested on cheap stocks; edge concentrated in small, thinly followed firms | Health check on large caps, not an edge |
| G-score | Built for growth stocks; needs industry medians | Growth names only; needs peer data |
| Altman Z | Built on manufacturers; young growth firms can read "distress" while healthy | Z'' for non-manufacturers; pair with runway; skip financials |
| Normalized earnings | Assumes the next cycle resembles the last | Show beside trend; owner review |
| Segment data | Segment definitions get restated | Track restatements; flag breaks |

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

## Open questions
- Peer groups: approved as D19; owner overrides to be entered at setup.
- Calibration window and test set for thresholds.
- Red flags still to design (ask first, D7): earnings quality (restatement deltas from the point-in-time store; 8-K Item 4.02; profit from estimate changes, the GE pattern); dilution (share-count growth, S-1/S-3 shelves — owner's pressure-signal code as a start); going-concern and covenant language via FTS5 exact phrases; unit economics (the Rivian pattern).
