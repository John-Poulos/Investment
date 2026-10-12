# M04 Round 2 — Earnings quality — brief

Updated for Round 1 answers (D-M04-2…13): CFO/NI warning routes on the D-M04-7 stage (mature and decline only) after the owner's confirmation (D-M04-12); D-M04-8 tag names (`asset_treasury` → NI, accruals, M-score "not meaningful"); rows per D-M04-9; 2.9 settled by D-M04-11; useful-life changes mark `capex_split` (D-M04-6).

**Outline:** Red Flag 3 (GE, Rivian; l. 80); R2, R11, D8, D21/D28.

## What the research says
- Accruals, M-score and misstatement score are screens with many false alarms (S-new-6…13); only the M-score and the misstatement score at high cut-offs gave a net benefit (S-new-15). M-score: investigate above −1.78; SGI pushes growers up (S-new-14). Misstatement score: > 1.00 flags 36.3% of clean firm-years; > 2.45 flags 5%, catches 18.8% (S-new-16).
- Restatements: 4.02 is waived when reported in a 10-K/10-Q; little r is about 76% of restatements (S-new-17, -18, -r2-1, -r2-2). Most first-vs-latest deltas are recasts; shifts raising CFO are a manipulation channel (S-new-r2-3).
- About 500 material estimate changes a year, mostly income-increasing; GE booked over $1.4B in 2016 (S-new-20, -21). Rivian: unit economics in Round 5 (R11); write-downs ($920M 2022, $107M 2023) under 2.6.

## Worked example
GE restatement walk (S-new-1, -r2-8, -r2-9; GE FY2018/FY2019 10-Ks; $M). Columns are the 2.3 tolerances applied to what is left after labelling.

| # | Step (first → latest) | Label after text | Left over | 2.3 (a) 0.5% and $0.1M | (b) min(1%, 5% pretax) | (c) 2% |
|---|---|---|---|---|---|---|
| 1–2 | Revenue FY2016 −4,224; FY2017 −3,849 | ASC 606 + other income (8-K 2018-04-13) | +1, 0 | — | — | — |
| 3 | Revenue FY2017 −18,964, NI unchanged | `reclass`: discontinued ops (passage attached) | — | — | — | — |
| 4 | NI FY2016 −1,331 | ASC 606 −1,182, LIFO→FIFO −147 | −2 | — | — | — |
| 5 | NI FY2017 −2,698 | ASC 606 −2,668, LIFO→FIFO −124 | +94 = NCI share | — (NCI label) | — | — |
| 6 | CFO FY2016 +1,404 | `cf_shift_up` 1,400 (watch) | +4 on a −244 base | **review** | review | — |
| 7 | CFO FY2017 −4,394 | ASU 2016-15 −4,411; restricted cash −153 | +17 | — | — | — |
| 8 | CFO FY2017 +522 | `cf_shift_up` 523; cause, no amount | — | flag | flag | flag |
| — | Infleqtion Q1 2026 revenue +$446K / net loss −$544K (little r; untagged after 2026-02-13, D-M04-8) | `error` (10-Q text) | — | both | both | net loss **missed** |

(a) queues one GE item (step 6); (c) none, but misses Infleqtion's net loss and Boeing's 0.66–1.78% revisions. GE 2016 estimate change: 2,200 ÷ 9,030 = 24.4% → watch (provisional).

Scores (2.1; scratch, recompute at build): NVIDIA FY2025 M −0.96 / SGI = 1 −1.98 / F 3.11 · NVIDIA FY2026 −1.17 / **−1.75** · Marvell FY2026 −1.60 / −1.98 · Apple FY2025 −2.29 / −2.35 / F 1.30 · Microsoft −2.54 / −2.67 / F 1.15 · Boeing FY2024 incomplete / F 1.63 · Strategy F 3.28 → not meaningful (`asset_treasury`, D-M04-8) · Micron FY2023 M −7.01 → not meaningful (negative gross margin).

## All cases
| Outcome | Cases (pack numbers; + added) |
|---|---|
| Error events | 1 4.02(a)/(b); 2 Big R in 10-K/10-Q only; 3 little r; 4 out-of-period; 21 auditor change within 12 months (escalates); 22 pre-2004-08-23 → no 4.02 history |
| Mechanical labels | 5 standard adoption; 6 discontinued ops; 7 segments; 8 split; 9 tag switch; 10 rounding; 11 8-K/DEF 14A excluded; 28 de-SPAC `predecessor`; +NCI share; +restricted cash |
| Watch or note | 23 CFO shift (up watch, down note); 18 factoring; 13–14 estimate change, recurring; 15 catch-up revenue; 16 contract-asset / deferred-revenue gaps; 29 fair-value swings; 30 valuation allowance; +Intel 2023 useful life 5 → 8 years → note and `capex_split` tag (D-M04-6) |
| Review | 12 mixed step; 24 shift plus residual; 25 near-zero base; 26 cause in an intervening filing; 27 cause without amount |
| Not meaningful / missing | 17 NI ≤ 0 or near zero; 19 growth in SGI and accruals; 20 missing inputs → "missing: <reason>" (D-M04-9); 31 negative gross margin; 32 unclassified balance sheet; `asset_treasury` (D-M04-8) |
| Excluded | `financial`, `reit`, `fund`, `spac_shell` (INFQ before 2026-02-13); untagged FF12 group 11 → "not applicable" (D-M04-8, replaces SIC 6000–6799); 33 foreign filer, 4.02 silent |
| Pending | +"one-time" charges, non-GAAP gap (2.6); +open 4.02 (2.8); +estimate amount later restated (GE $2.2B → $0.7B) → by filing version |

Settled: unassigned or ambiguous stage (D-M04-7: last confirmed stage routes; first run both flag sets labelled, uncounted).

**Completeness:** complete for revenue, NI and CFO on the watchlist. From the rules only: 4.02(b), Big R via B.3, 10-K/A. Other concepts not walked; SPCX has no annual history.

## Suggestions
- **S2.1** `eq_cash` (CFO/NI, cash-flow accruals, operating basis); not meaningful when NI ≤ 0 or |NI| < 1% of revenue; tax 21% (2018 on) / 35% unless stated. *Changed:* tags per D-M04-8; routing per 2.7 on the confirmed D-M04-7 stage; "not meaningful" is a `value_text` state (D-M04-9).
- **S2.2** `credit.dso()`, `contract_asset_gap`, `deferred_rev_gap`. Alias-to-standard tag switch → "definition changed", window not scored (D-M04-3 rule).
- **S2.3** `mscore` with SGI = 1 variant; ACCR variant named (1999 original unverified).
- **S2.4** `misstate_f` "approximation", bands > 1.00 / > 2.45; `issue` unknown → missing, never 0.
- **S2.5** `restatement` (4.02, dei flag from R1 pages, text, 4.01 escalation); one count (36) pack-wide.
- **S2.6** `restate_delta` walk, ordered labels incl. NCI share and restricted cash, first-run baseline.
- **S2.7** `estimate_share`; amounts by filing version; a useful-life change marks that year's depreciation-rung maintenance capex (D-M04-6 default; Intel 2023).
- **S2.8** Information only until D13 weights; rows per D-M04-9 (e.g. `value −0.160`, `value_text "reclass"`). `eq_cash` and Piotroski's CFO > NI count the same evidence.
- **S2.9** Fixtures: GE rows 4–7 and its estimate.
- **S2.10** Review kinds inside the M04 cap, B.3a order; reconcile the walk baseline (B.3 101; here 102/135).
- **S2.11** *If 2.6a:* `special_items`.

## Check flags
- Red Flag 3 "one-time" had no signal → 2.6; open 4.02 unlinked → 2.8; FCF growth → D-M04-11. CFO/NI sign flip with a loss (NI −100, CFO −50 reads 0.5) → S2.1.
- Names: stage D-M04-7 (was "5.1"); tags D-M04-8 (Round 3 adopts `asset_treasury`). 2.1 credits both screens; 2.4a fetches two prior 10-Ks.
- Add failure modes: alias-to-standard tag switch; tax-rate approximation. No conflict with D16, D27, M01 rules 3 and 7 unless 2.8(b).

## Gaps
**Closed:** Alphabet 2023 lives 4 → 6 years, NI +$3.0B (S-new-22). GE NI residuals −2, +94 (= NCI; FY2018 10-K pp. 108, 111); CFO FY2017 ASU 2016-15 −4,411, restricted cash −153 (p. 110); FY2017 recast does not tie → passage attached; estimate $2.2B → $0.7B (provisional: "DRAFT" print, pre-tax assumed). Amazon ASU 2016-09 amounts stated. Tax 21%/35% (§11(b)).

**Needs the owner's probe:** GE FY2017 10-K (1 request) for the $2.2B sentences. Local, no SEC: `fact` tags for NVDA, MRVL, TSLA, GFS; recompute scores; SPCX 10-K count. Open: Beneish 1999 ACCR; unsourced thresholds.

## Questions
**2.1 Score set and role**
- (a) (recommended) Cash conversion and accruals as persistence warnings, no return weight; M-score with and without SGI = 1, review only when SGI = 1 is above −1.78; misstatement score with both bands, no trigger. Why: screens, not signals; SGI = 1 removes growth alarms. Today: one review (NVIDIA FY2026); NVIDIA FY2025 and Marvell get a "growth-driven" note. Gets wrong: a manipulator whose score rests on sales growth gets only that note (illustrative).
- (b) Both scores at published cut-offs. Gets wrong: flags NVIDIA and Marvell on growth; Apple, Microsoft and Boeing sit in the > 1.00 band holding 36.3% of clean firm-years.
- (c) Cash conversion only. Gets wrong: drops both screens with a net benefit; misses NVIDIA FY2026's AQI jump (1.52).
- (d) As (a), plus `misstate_f` > 2.45 as a trigger. Gets wrong: queues NVIDIA FY2025 (3.11, growth and issuance; 1.12 with `issue` = 0).

**2.2 Restatement sources and escalation**
- (a) (recommended) 4.02 + dei flag + 10-K/10-Q text + one-off fetch of at most 35 old filings; a 4.01 within 12 months escalates. Why: catches little r (Infleqtion ticks no box); labels GE. Gets wrong: causes without amounts stay review items.
- (b) 4.02 only. Gets wrong: misses Infleqtion's little r and GE's recast causes.
- (c) As (a) without escalation. Gets wrong: drops the auditor-change signal (29% of Big R vs 11% base).
- (d) As (a) without the historical fetch. Gets wrong: about 102 pre-corpus steps stay `unexplained`.

**2.3 Tolerance for unexplained deltas**
- (a) (recommended) Review above both 0.5% and $0.1M, after the S2.6 labels. Why: creates both Infleqtion steps a $1M floor missed. Gets wrong: queues GE FY2016's +$4M on a −$244M base.
- (b) Above min(1%, 5% of pretax income; void when pretax ≤ 0). Gets wrong: shrinks with profit (Intel FY2023 $38M vs $271M).
- (c) Above 2%. Gets wrong: misses Infleqtion's net-loss correction (1.8%) and Boeing's revisions.

**2.4 Estimate changes and prior filings**
- (a) (recommended) Bands < 10% / 10–25% / ≥ 25% of the 2.5 denominator, both directions; two prior 10-Ks each (at most about 28 requests; ETV and INFQ's shell years skipped, D-M04-8), closing DS7. Why: a 3-year test needs three disclosures. Gets wrong: SPCX gets no recurrence test.
- (b) Any quantified change is a note; prior 10-Ks wait for M06/M11. Gets wrong: Alphabet and Intel 2023 judged alone.
- (c) Income-increasing only. Gets wrong: hides Amazon 2025 (NI −$1.0B).

**2.5 Estimate-share denominator**
- (a) (recommended) Company figures on the amount's tax basis and period; not meaningful when ≤ 0 or below 1% of revenue; segment share only when stored or quoted. Why: always available; GE reads watch either way. Gets wrong: GE Power's 29%/45% stays hidden until segment profit is stored.
- (b) Segment profit when attributed. Gets wrong: missing for most names until 5.4.
- (c) Company net income only. Gets wrong: pre-tax amounts over after-tax income (illustrative: 35% rate, 1.54× too high).

**2.6 Recurring "one-time" charges** (outline Red Flag 3)
- (a) (recommended) `special_items`: restructuring, impairment and write-down tags plus FTS5 "non-recurring"/"one-time" in ≥ 3 of 4 years (starting value); cumulative size vs operating income; the stated non-GAAP vs GAAP gap, quoted, never computed (D-M02-29). Why: the outline's pattern; excluded costs predict lower cash flows (Doyle et al. 2003; McVay 2006 → S-new-r2-10/11). Gets wrong: a genuine multi-year restructuring reads as recurrence (shown with its plan).
- (b) Round 5's "excluding stated items" margin. Gets wrong: gross margin only; the non-GAAP gap never shows.
- (c) No signal. Gets wrong: GE's and Rivian's pattern is never measured.

**2.7 Which Round 2 flags are stage-routed** (narrowed: the stage rule and unconfirmed stages are settled by D-M04-7 and D-M04-12)
- (a) (recommended) Events, M-score (SGI = 1), `misstate_f` and the revenue gaps are stage-neutral; CFO/NI < 0.8 warns for mature and decline, a note for introduction, growth and shake-out; accruals vs own history, no warning. Shake-out moved to a note: D-M04-7 already reviews every held shake-out. Today: AAPL and MRVL can warn after the setup batch (D-M04-12); TSLA's "growth" routes only once confirmed. Why: only cash conversion is mainly a growth effect. Gets wrong: a growth firm with real collection problems gets a note (illustrative).
- (b) Everything stage-neutral. Gets wrong: young firms building receivables warn on growth.
- (c) All Round 2 flags become notes for introduction and growth. Gets wrong: a young firm's 4.02 or little r is only a note.

**2.8 Open 4.02 and other M04 outputs**
- (a) (recommended) Until the restated filing, rows reading the affected periods (CvD, gate, F/G/Z, `guidance_hit_rate` of D-M04-10) are marked "inputs under non-reliance" and warn; adds not blocked (D16). Why: the doubt shows without overruling M01. Gets wrong: an M01 add can still trigger on disowned figures.
- (b) As (a), and the gate reads "incomplete" (no adds). Gets wrong: a small, quickly restated error (illustrative: one quarter's revenue) stops adds for months.
- (c) No link. Gets wrong: M01 reads non-reliance figures unmarked.

**2.9 Where FCF growth lives** — settled by D-M04-11 (`fcf_growth`, two bases, information row); S2.1's near-zero-base rule carries to it. No answer needed.
