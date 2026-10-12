# M04 — Financials & red flags

Status: CvD profile approved; design review in progress (Round 1) · Updated: 2026-10-12 · Outline headings: Analyze the financials; Financial red flags · Depends on: M00 (SEC data), M02 (peer data), M06, M11 (R19 ledger) · Sources: S02–S04, S13, S20, S25, S32–S37, S43–S45

## Purpose
Judge financial health and earnings quality, and classify a slowdown as a cyclical trough or a structural decline (CvD) for M01's entry and exit rules.

## Decisions carried from DESIGN.md
- Red flags are stage-aware; ambiguous stage → review queue. (R2)
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
- Round 1 suggestions S1.1–S1.6, S1.8, S1.9, S1.11, S1.12 accepted (owner "rest ok"; texts in docs/m04_review/R1_brief.md); S1.7 and S1.10 follow 1.9 and 1.6/1.11.

## Open questions
- Peer groups: approved as D19; owner overrides to be entered at setup.
- Calibration window and test set for thresholds.
- Red flags still to design (ask first, D7): earnings quality (restatement deltas from the point-in-time store; 8-K Item 4.02; profit from estimate changes, the GE pattern); dilution (share-count growth, S-1/S-3 shelves — owner's pressure-signal code as a start); going-concern and covenant language via FTS5 exact phrases; unit economics (the Rivian pattern).
