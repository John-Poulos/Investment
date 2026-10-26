# M11 Thesis, sizing & killswitch — MVP brief
**Decided 2026-10-25 → docs/M11_THESIS.md** (D-M11-1…8; every recommended option and default; tiers D-M01-10; Q11.9a money-flow writer D-M02-64). Kept as the sitting record.
Updated 2026-10-25 (refreshed for sitting 5) · Source: docs/M11_DESIGN_PACK.md (research) · Status: for owner decision (sitting 5)

Outputs are research signals and warnings, not financial advice (D16). Answers become D-M11-1 onward in a new `docs/M11_THESIS.md`. The tier amendment (Q11.4) takes D-M01-10, and the money-flow writer design (Q11.9, plan QP.2a) takes D-M02-64.

## Since 2026-10-13 (what the refresh changed)
- **Every confluence input except M02, M03 and M06 now writes rows:**
  - M04 8a: `cvd_state`, `f_quality`. 4b-lite: `gc_language`, `covenant_status`.
  - M07: `insider_buy` and the others.
  - M09: technicals.
  - M08: `est_revision` and the standard rows.
  - M05: `capex_demand` with its vote in `method`; `commitment_cover`.

  M06 and M03 come in W6–W7, before M11's build (W8–W9); M10 Part 1 builds alongside M11 in W8.
- **Vote lines confirmed in sittings 1–4** replace the brief's starting map:
  - M07 votes with `insider_buy`, not `insider_net_flow` (D-M07-2: opportunistic +1, no qualifying buy = missing).
  - M05 votes with `capex_demand`'s built vote line (D-M05-7).
  - M06 votes with `moat_verdict`, and `moat_gate` blocks a first MY entry (D-M01-9).
  - M03 is **medium** tier, not low (D-M01-8).
  - M08 keeps `est_revision` (D-M08 note, settled here).
  - M10 has no vote (all info, D-M10-8).
- **The 8a reality changes M04's vote.** On the 2026-10-13 CvD log every active name reads NO_SLOWDOWN (confidence —), so under the starting map M04's vote is the `f_quality` band for every name today:
  - 4–5 points: AAPL, AMZN, GFS, GOOG, INTC, MRVL, MSFT, MU, ORCL, TSLA.
  - 3 points: META.
  - 1 point (weakening): RIVN.
  - missing: AVGO, BA, INFQ, MSTR, NVDA.

  INTC reads +1 because F-quality scores year-over-year improvement, not level (flag below).
- **M01's rule readers are built** (`m01_rules.py`: rules 1, 3, 4, 7). `size_cap`'s no-add gate and `exit_warning`'s rule-4 reasons read them, never a copy. The rule-4 list now includes AHEAD_OF_DEMAND (D-M01-7).
- **New real exit trigger:** NVDA's CvD line reads "exit warning: guidance_removed 2026-05-20 (quietly removed targets)".
- **Hurdle inputs arrive in W8.** SPY is stored (M09), and CPI comes from M10 Part 1 (D-M10-3). The R5 hurdle can therefore be shown in Part 2 at 0 new fetchers: default below.
- **M10 decided** (sitting 4): `policy_event_exposure` (M10 Part 2, W9) is Q11.6a's "ban on AI" input. M10's `move_note` sentence shows on the Thesis tab. `macro_exposure_warning` is shown on the Thesis tab, never a trigger (info).
- **M05's fabless gap:** `capex_demand` reads "vote: none" for fabless and outsourced names (R9). Their leading data is `commitment_cover` (D-M05-24, fabless MY ✓). Q11.4a now maps it as M05's vote for those channels.
- **Plan QP.2a:** the thin M02 money-flow writer is designed here (new Q11.9).
- **Pre-assigned numbers** (MVP_PLAN):
  - Part 1: `0046_m11_thesis`, D-STO-36, D-UI-45 (Thesis tab, Portfolio page), DS24 (broker import).
  - Part 2: `0048_m11_caps`, D-STO-38, D-UI-47 (confluence line, theme exposure).
  - Waves W8 and W9.

## D32: standard rows for every company, and rules whose evidence is tech-only
**Standard rows (default; strike if you disagree).**
- Every company gets a confluence line, including "0 of n". Each module's vote is listed with its state, grade and date, or its missing reason.
- Every held position shows all three caps, binding or not, plus standard risk measures: σ60d, σ1y, the 1-year maximum drawdown and the portfolio weight.
- Every lot shows its age, with the "< 1 yr" note.
- Once M10 Part 1's CPI lands, the R5 hurdle is shown on Portfolio: lot return minus SPY total return, and the CPI stretch. This is a display line, not a D13 row (Part 2). The vote map changes only what counts, never what is shown (D10).

**Tech-only evidence (D9 failure modes, checked on non-tech names at tuning):**
1. **The vote map was built on a strong-year, mostly-tech watchlist.**
   - Every name reads NO_SLOWDOWN today, so M04's vote reduces to `f_quality`.
   - F-quality scores improvement (accruals, leverage, liquidity, equity, CFO). A decliner improving its balance sheet (INTC 4 of 5) votes +1.
   - The CvD grid is designed to override that in a slowdown. Until a slowdown occurs, the M04 vote is mostly a health check.
2. **The shared capex killswitch has one seeded theme.** `ai_infrastructure`'s spenders are five hyperscalers. Autos (EV capex), airlines (aircraft orders) and utilities (rate base) get a shared key only where M02 has a theme with confirmed spender links.
3. **KPI milestones score only where `unit_metric` holds the KPI.** Today that is Tesla deliveries (DS2). Other KPIs are owner-set (B).
4. **Non-tech evidence exists in the brief.** The Boeing slip example and the RIVN gate fail are an aerospace and an auto case. The vol cap (2% ÷ σ) and the theme cap are industry-neutral.
5. **Fixtures at build add two non-tech cases:** a utility with a rate-case milestone (owner-set), and a bank with "class not mapped" from M10.

## Purpose in one paragraph
For each held or watched name, M11 keeps a written thesis with dated milestones and exit criteria. It says whether the thesis is early, on track or wrong, raises killswitch warnings and gives a size ceiling. A **core** score (D13 "core computes"; M00 in D15) combines the modules' D13 rows per timeframe. Theses, milestones, kill criteria and sizing are **M11**.

Binding decisions: R4, R19, R5, R23, D11/D12, D13/D14, D16, D27, D-M01-5/-6, M01 rules 1–7, and R1 (M06: invest only with a moat). M04 settles three points:
- `guidance/record.py` is the shared scorer, and M11 extends it.
- "Withdrawn" is M04's `guidance_removed`.
- NO_SLOWDOWN is defined by D-M04-55.

M04's "How M01 reads M04" table (M04_FINANCIALS) settles which M04 states block adds and which raise exit warnings; M11 reads it as written.

**Against the outline** ("Entry, Size, Exit and Killswitch" 1–5; Technical Analysis 4; "Understand why" 4–5):
- Follows: the exit is written at entry (item 1); the killswitch includes "capex slowdown" (item 3); review after each 10-Q/10-K, "fill or kill" (item 5); confluence of signals (TA 4); "edge, not moving = early" (Understand why 5); "preserve capital" (item 4) through gate blocks and caps.
- Served elsewhere: "this asset is moving because…" (Understand why 4) is M10's `move_context` sentence; the thesis tab shows it.
- Departs:
  - Item 2 "optimise size" is only a ceiling (no Kelly or risk/reward).
  - Item 3 "ban on AI": read from M10's `policy_event_exposure` once M10 is built (Q11.6); until then an owner-written rule that code shows but does not check.
  - Item 4 opportunity cost (the R5 hurdle) is deferred. Its inputs come from other briefs: SPY (M09 Q09.6) and CPI/M2 (M10, keyless FRED), so "Analyze financials" 5 gets its data there.
  - TA 4 / M01 rule 1: the score is shown, but no entry threshold is set in the MVP (Q11.4).

## Data already stored that the MVP uses
| Need | Stored in (migration · code) | Gap |
|---|---|---|
| Module D13 rows | `signal` (0029, keyed by cik) · `signals.py`; M01 readers `m01_rules.py` | M04, M05, M07, M08, M09 write rows; M06, M03 (W6–W7) and M10 (W8) to come; M02 writes none (Q11.9) |
| Positions, lots, decisions | `position`, `lot`, `decision` (0001); nothing reads or writes them | Broker import: new gap (manual entry). `position.cik` is nullable and `decision` has no cik, thesis or criterion column: M11's migration adds them |
| Guidance and outcomes | `guidance` (0009, rebuilt 0013/0016), `guidance_outcome` (0030, rebuilt 0031) · `guidance/record.py`, `changes.py` | Non-GAAP actuals missing (only non-GAAP gross profit for some, `unit_metric`); DS3 growth rates; DS1 calls (B) |
| M04 gates and reasons | signal rows `survival_gate`, `filing_status`, `guidance_removed`, `guidance_hit_rate`, red flags, `cvd_state`, `f_quality` (8a), `gc_language`, `covenant_status` (4b-lite) | None |
| Milestone sentences | open `guidance_unparsed` items held for M11 (Boeing 777-9; D-UI-14/15) | — |
| KPI actuals | `unit_metric` (0035; Tesla deliveries, DS2 built) | DS14 partly |
| 8-K events | `event` (0006) | — |
| Prices | `price_bar.adj_close`, `split_factor`, `price_fetch` (0012); SPY stored (M09 Part 1) | CPI from M10 Part 1 (W8, D-M10-3) |
| Themes | `theme`, `theme_company` (active; keyed by ticker) (0014), `spender_link` (0019), `capex_stated` (0019) | — |
| Quote checks | corpus documents; `llm/verify.quote_found`, `review.store_owner_row` (D-UI-14 owner entries) | Prior-year 10-Ks (DS7, partly) |

## MVP signals (4)
Every row follows D13 / D-M04-9: keyed by cik (D-M04-74), one row per timeframe, numbers in `value`, states in `value_text`, missing = "missing: <reason>" (never 0), grade = weakest deciding input, `source_ref` = newest accession "+N". M01 defines MY only, so PT and ST reuse the MY weights, labelled in `method`. When one cik has several theses (D11), the row shows the worst state and `method` lists each one. A shared (theme) killswitch is written on every linked cik's `exit_warning` row.

| Signal | value / value_text | Meaning | Inputs | MY | PT | ST | Grade |
|---|---|---|---|---|---|---|---|
| `confluence` (M00, core) | [−1, 1]; text `split`; no votes = missing row "0 of n"; "k of n" and the vote vector in `method` | Σ w·g·s ÷ Σ w·g over reporting, non-stale votes; **one headline vote per module** | vote map `config/confluence.toml`; M01 tiers | ✓ | ✓ | info | weakest counted vote |
| `thesis_state` | `no_thesis` / `early` / `on_track` / `review` / `exit_warning`; milestones and M01's `review_due` in `method` | R4 early vs wrong; quarterly fill-or-kill review | thesis, milestones (guidance-linked via `guidance_outcome`), price since the thesis date, `cvd_state`, latest 10-Q/10-K | ✓ | ✓ | ✓ | weakest deciding milestone (owner-only = B) |
| `exit_warning` | `armed` / `warning` / `hit` / `acknowledged`; reasons and sources in `method` | M01's `exit_warning` (rule 4) per thesis plus the shared theme key (D16) | M01 rule-4 reasons from M04, thesis-metric guide cut, milestone rule, owner-picked 8-K items, shared capex rule, M10 policy rows (when built), `owner_rule` (shown only) | ✓ | ✓ | ✓ | weakest deciding input; a `hit` needs A, or B confirmed by a second source |
| `size_cap` | % of portfolio; text = the binding cap, `blocked: <gate>` or `over_cap: <theme>` | A ceiling, not advice; also the rule-1/rule-3 no-add gate | owner cap, risk budget ÷ max(σ60d, σ1y), theme headroom, gates | ✓ | ✓ | ✓ | A when the vol cap binds (D-M04-82); B when headroom from owner-entered lots binds (D-M04-9) |

**Rules for `confluence` and `size_cap`:**
- A missing vote leaves the denominator, never 0 (D-M04-56).
- Grade weights: A 1, B 0.5, C 0 (C is shown).
- **Exit warnings** (M01 rule 4, decided): gate fail, overdue filing, CvD CYCLE_PLUS_DAMAGE or STRUCTURAL_DECLINE, `guidance_removed`.
- **No-add** (`size_cap` blocked), read from M04's table: later tranches (rule 3) need CvD CYCLICAL_TROUGH or NO_SLOWDOWN with gate pass/warn, so AMBIGUOUS/STUMBLE (open `m04_cvd`), damage, decline, overdue, gate fail, incomplete or not applicable all block. A first entry (rule 1, D-M01-6) needs gate pass/warn, no overdue filing and CvD not damage/decline. M06 `moat_gate` not met blocks a first MY entry (R1; per Q06.5). CvD missing (before 8a) reads "blocked: cvd missing" for tranches, never a pass.
- Technicals time the entry (M01 rule 1) and stay out of the average.
- M04 red flags are listed as reasons and never block (D-M04-21, -60).
- A vote is stale after 120 days (MY/PT) or 10 days (ST); starting values.

## Worked example
**Boeing 777-9 first delivery** (S-new-M11-18; the 2027 sentence is an open item in the real queue):
| Version | Target | Charge | Source |
|---|---|---|---|
| v1 2022-04-27 | 2025 | not found | AirInsight (secondary, B) |
| v2 Q3 2024 | 2026 | $2,608M reach-forward loss | FY2024 10-K (A; not stored, DS7) |
| v3 2025-10-29 | 2027 | $4.9B pre-tax | 8-K EX-99.1 0001628280-25-046915 (A) |

Two slips. Under Q11.3a the v2→v3 slip carries a charge on grade-A documents, so `thesis_state` is exit_warning and `exit_warning` hit (A); under 3b both read `review`. BA's real M04 rows: the gate passes, and an open `m04_score_gap` (Z 1.53, distress) is listed as a reason but does not block. With `cvd_state` missing, BA is never `early`.

**Other real triggers:**
| Name | Stored fact | M11 result |
|---|---|---|
| RIVN | gate fail on the real DB (Part 4a re-run 2026-10-13); 5,310 ÷ 962 = 5.5 q is the Part 4a fixture | `exit_warning` hit; `size_cap` blocked |
| MSTR | FY2026 EPS, net income and operating income guides `removed` (Part 1b re-run) | `exit_warning` hit, reason "quietly removed targets" (M01 rule 4) |
| NVDA | Q1 FY2026 GAAP GM guide 70.1–71.1% vs 60.52%; hit rate 92% | linked milestone `missed` → `review` |
| SPCX | gate `incomplete` | `size_cap` blocked (D-M04-35); no exit warning |

**Shared `hyperscaler_capex`** (theme `ai_infrastructure`: NVDA, MSFT, AMZN, GOOG, META): Alphabet raised its 2026 guide to $195–205B from $180–190B (S80, call, B). Nobody lowered, so the state is `armed`.

**Confluence today (real rows from the module logs, under the refreshed Q11.4a map and D-M01-8's tiers; 7 tiered modules: M02, M04, M05, M06 lead 3; M07, M03 medium 2; M08 low 1):**

| Name | M04 (w 3) | M05 (w 3) | M08 (w 1) | M07 `insider_buy` (w 2) | M02, M06, M03 | Score |
|---|---|---|---|---|---|---|
| MU | NO_SLOWDOWN → `f_quality` 4 of 5 → +1, A (cvd log 2026-10-13) | BUILD_INTO_DEMAND, vote positive → +1, A (demand log 2026-10-21) | `est_revision` +13.08% up → +1, B (Alpha Vantage, 2026-10-21) | no qualifying buy → missing | missing (not built / no writer) | (3 + 3 + 0.5) ÷ 6.5 = **+1.00, "3 of 7"** |
| RIVN | `f_quality` 1 of 5 (weakening) → −1, A | INSUFFICIENT_HISTORY, vote neutral → 0, A | no estimate snapshot → missing | missing | missing | (−3 + 0) ÷ 6 = **−0.50, "2 of 7"**; gate fail → `size_cap` blocked, `exit_warning` hit |
| NVDA | `f_quality` missing (1 point decides the band) | fabless: `commitment_cover` short_history 3.64 → missing (no year-ago point) | no snapshot → missing | missing | missing | **missing row, "0 of 7"**; rule 4 `guidance_removed` 2026-05-20 → `exit_warning` hit on a thesis |

MU's unanimous +1.00 rests on 3 of 7 modules: this is why "k of n" is always shown and why no entry threshold exists until ≥ 3 lead modules report.

**Earlier example, MU MY at the 2023-10-06 10-K (8a expected value; illus. M05 and M07):**
| Vote | s | g | w |
|---|---|---|---|
| M04 `cvd_state` CYCLICAL_TROUGH (8a expected value, conf. 1.00) | +1 | 1 | 3 |
| M05 `capex_demand` (illus.) | +1 | 0.5 | 3 |
| M07 `insider_net_flow` (illus.) | −1 | 1 | 2 |
| M02, M06, M08, M03 | missing | — | out |

(3 + 1.5 − 2) ÷ 6.5 = **+0.38**, "3 of 7 tiered modules". With M04 alone, as today, the score is +1.00 with "1 of 7", which is why k of n is always shown.

**size_cap (illus. figures, real formula):** owner cap 10%; 2% ÷ σ 55% = 3.64%; theme 25% − 11% = 14%. The cap is **3.64%, bound by volatility**.

## Cases the rules must handle
1. Held position with no thesis (incl. lots entered before M11): `no_thesis`. A watch-only thesis gets every state and its kill criteria.
2. An edit makes a new version, never an overwrite; a thesis written after the move is a rationalisation (S-new-M11-3).
3. No measurable target or due date: `narrative`, never scored.
4. Guidance milestone follows `guidance_outcome`: hit → hit; miss → missed; pending → open; removed / expired → withdrawn; dropped → shown, never a trigger (D-M04-85); unscored / missing → unscorable with the reason.
5. Non-GAAP guide without a stated actual, or `definition changed`: unscorable, never a miss (Microsoft leases).
6. Walk-downs: the shared scorer uses the latest guide (D-M04-10); revisions are counted and the walk shown (S-new-M11-2).
7. Event target restated: `slipped`; due date passed, no hit: `missed`; a charge is entered with its quote.
8. Owner milestone: `owner` (B), kept out of company credibility.
9. On track, price flat or down, CvD not damage/decline: `early` (M01 rule 5); CvD missing: "on track, CvD missing", never `early`.
10. A 10-Q/10-K filed after the last review: `review` and `review_due`.
11. One grade-B input stays `warning` until a second source confirms; grade C never fires.
12. Price drawdown alone is context, so a cyclical is not flagged at its trough (MU 2022–23; S-new-M11-15).
13. A spender's own position: its capex cut counts against it too (D-M02-5); the owner can unlink it.
14. Acknowledgement writes a `decision`; the warning repeats only if the trigger worsens, deduplicated per criterion and week (S86).
15. Closed position: its criteria deactivate; a shared key stays while any linked position remains.
16. No votes: missing row, "0 of n"; opposite lead signs: Q11.5; stale votes excluded and marked.
17. Two modules on one input family (M02 money flow, M05 capex on `capex_stated`): one vote, declared in the map.
18. Several active themes: full weight in each; proposed membership shown, not counted.
19. Fewer than 60 bars (SPCX from 2026-06-12): vol cap missing, other caps apply; none computable → missing row.
20. Low volatility before a shock: vol only caps; tranche adds follow M01 rule 3.
21. Above cap after a rise: `over_cap`, never a forced trim (D16); no portfolio value → caps in % only.
22. Overlay: own thesis and profile (D11), options wait for M12; viewing-profile switches logged, profile of record kept (D12).
23. Ticker change or split: keyed to cik and position; quantities via `split_factor`.

## Deferred to the tuning phase
- **R19 credibility card** (signed bias, |error_hw|, horizon weights) and scoring against the *first* guide (pack 2.1a; the shared scorer uses the latest, D-M04-10): M04's `guidance_hit_rate` stands in. The weights need scored history.
- **Non-GAAP stated actuals** (need a reconciliation store) and **Brier scores** (need owner probabilities).
- **Conviction tiers and the ½-Kelly ceiling:** owner edge estimates oversize positions (S-new-M11-11).
- **Hurdle** `hurdle_excess` / `stretch_excess` (R5 fixed): needs lots, SPY (M09 Q09.6) and CPI (M10); 0 new fetchers for M11 once those land.
- **M01 rule-1 entry threshold and `entry_plan`**, `lot_status` as a D13 row (lot age and the "< 1 yr" note are shown on Portfolio).
- **`m11_kill_hit`, `m11_cap_breach` and disagreement review kinds, and caps on shared keys beyond themes.**
- **Broker import** (depends on the broker), **pre-mortem** (weak evidence, S-new-M11-4), **turnover display** (no decision history yet).

## Questions for the owner
**Q11.1 Thesis scope and the written exit**
- a) One versioned thesis per position plus watch-only theses; lots entered by hand; a thesis is saved only with at least one kill criterion. (**Recommended**: outline Entry 1, "know exit before entry"; pre-commitment, S-new-M11-3.)
- b) The same, with kill criteria optional.
- c) Held positions only.

**Q11.2 Milestones**
- a) Two kinds:
  - guidance milestones linked to a ledger row, taking M04's outcome;
  - event or KPI milestones with a target and due date, quoted from a stored document (A) or noted only (B); KPI status from `unit_metric` where stored (DS2), else set by the owner.

  Plus a "Make milestone" action on the open `guidance_unparsed` items. (**Recommended**: closes D-UI-14 and reuses the shared scorer, per the M04 note.)
- b) Guidance milestones only.

**Q11.3 A slipped milestone (Boeing)**
- a) `exit_warning` at the second slip or at any slip with a charge; one slip without a charge gives `review`. (**Recommended**: a charge is hard evidence that the delay costs money, S-new-M11-18.)
- b) Every slip gives `review` only.

**Q11.4 Confluence: votes, weights, threshold** (home = core, D13)
- a) `src/engine/confluence.py`, module_id `M00`:
  - one headline vote per module in `config/confluence.toml`, starting map (refreshed with the vote lines confirmed in sittings 1–4):
    - M04 `cvd_state`: CYCLICAL_TROUGH +1; NO_SLOWDOWN → `f_quality` ≥ 4 +1, 3 → 0, ≤ 2 −1; STUMBLE / AMBIGUOUS 0; damage / decline −1.
    - M05: `capex_demand`'s vote line (positive +1, neutral 0; D-M05-7). For fabless and outsourced channels, `commitment_cover` instead: RISING +1, FALLING −1, FLAT 0, short_history missing (no year-ago point).
    - M06 `moat_verdict`: WIDE +1, NARROW +0.5, NONE −1, UNRATED / N_A missing.
    - M07 `insider_buy` (D-M07-2): opportunistic +1; no qualifying buy missing, never 0.
    - M08 `est_revision`: up +1, flat 0, down −1, not_meaningful missing.
    - M03 `curve_stage.*` of the largest mapped curve: emerging / accelerating +1, past_inflection 0, declining −1.
    - M02 `money_flow` (Q11.9).
    - M10 none: its rows are info (D-M10-8).
    - M09 none: technicals time entries (M01 rule 1).
  - equal weights within M01's tiers: lead 3 (M04 fundamentals, M06 moat, M05 capex, M02 money flow), medium 2 (M07 ownership; M03 per D-M01-8), low 1 (M08 analysts). Recorded as D-M01-10 (MVP_PLAN overlap 2);
  - technicals excluded; grades A 1 / B 0.5 / C 0; no entry threshold until ≥ 3 lead modules report (tuning).

  (**Recommended**: simple weights match fitted ones on small samples, S-new-M11-8, -9; one vote per module avoids double counting.)
- b) An owner-set weight per module.
- c) Every module signal counts.

**Q11.5 Lead modules that disagree in sign**
- a) No single score: the text reads `split` and the vector is shown, with no review item. (**Recommended**: an average hides the conflict, D10; fewer queue items, S86.)
- b) Always show the score, with a split mark.
- c) No score, plus a review item (pack 3.3a).

**Q11.6 What else may fire a killswitch** (M01 rule-4 reasons fire already)
- a) Code also fires on:
  - a thesis-metric guide `lowered` (a `definition changed` row blocks it);
  - the Q11.3 milestone rule;
  - 8-K items the owner picks;
  - M10 `policy_event_exposure` confirmed or stated on a topic the owner picks ("ban on AI"), once M10 is built.

  `owner_rule` is shown only. A hit needs grade A, or B confirmed by a second source. Price drawdown is context only. (**Recommended**: price stops lower returns without momentum, S-new-M11-15; D16.)
- b) The same, plus a price stop as its own trigger.

**Q11.7 Shared capex killswitch (outline "capex slowdown")**
- a) Keyed by theme: `warning` when one spender with a confirmed `spender_link` to the theme lowers its current-year capex guide (`changes.py`); `hit` when 2 or more lower in the same season (starting value). (**Recommended**: D-M02-5 has no cross-company totals in v1, and one cut can be a reallocation.)
- b) The pack's rule, the sum falls ≥ X% from its peak. This needs D-M02-5 changed.
- c) Any one cut is a `hit`.

**Q11.8 Sizing**
- a) `size_cap` = the minimum of the owner per-position cap, risk budget ÷ max(σ60d, σ1y), and theme headroom (full weight per active theme); a no-add gate gives 0 with the gate named. Conviction and Kelly come later. (**Recommended**: each cap guards a different risk; volatility mainly trims tails, S-new-M11-12; R23 needs the theme cap.)
- b) Owner cap and theme headroom only.
- c) No sizing until tuning.

**Q11.9 The thin M02 money-flow writer** (plan QP.2a: built in W10, designed here)
- a) A supplier-side `money_flow` row, module M02. It covers a company with a confirmed `supply_link` (L1–L3) as the supplier of a spender that has a confirmed `spender_link` to an active theme. Readings for the latest guidance season (`guidance/changes.py` on the current-year capex guide):
  - +1 when at least one linked spender raised its guide (raised, or raised low or high end) and none lowered;
  - −1 when at least one lowered and none raised;
  - 0 when the moves are mixed or unchanged;
  - missing when there is no confirmed link or no stated guide.

  The spender itself gets no M02 vote, because its capex is already M05's vote (D-M02-62, case 17). Grade = the weaker of the guide and the link. MY carries weight (lead tier); PT and ST are info. (**Recommended**: D-M02-5 counts a capex rise as positive for the suppliers, and the research favoured suppliers. One input family gives one vote, and the inputs are built, so the writer costs 0 requests.)
- b) Spender and supplier rows both (the plan's literal wording). The spender's row and M05's vote are then declared one input family and counted once.
- c) No writer: money flow stays empty in the MVP (a lead tier with no votes, shown in "k of n").

Note: a lowered guide also drives Q11.7's shared capex killswitch. One is a vote and the other a warning, from the same stored change.

## Build parts (2)
**Part 1: Thesis, milestones, killswitch (M11)**
- **Code:** `src/engine/thesis/` (record, milestones, kill, step, views); a "Make milestone" action in `review.py`.
- **Numbers:** branch `m11-part1`, migration `0046_m11_thesis`, D-STO-36, D-UI-45, DS24 (broker import); decisions from D-M11-10.
- **Tables:** `thesis` (versioned), `milestone` (versioned; `set_by`, grade, quote reference), `kill_criterion` (`shared_key` = theme key); columns for cik on `position` and thesis/criterion on `decision`. It writes `position`, `lot` and `decision`.
- **Review kinds:** none. Kill hits are listed in the refresh's end-of-run alert box and a Portfolio banner (M01 rule 6), deduplicated per criterion and week.
- **Signals:** `thesis_state` and `exit_warning`, written in the logon local pass after M04's (0 requests).
- **UI:** a company "Thesis" tab (versions, milestones, criteria, reasons, M10's move sentence when built, an acknowledge button that writes a `decision`) and a Portfolio page (positions, lot entry, lot age with the "< 1 yr" note).
- **Live check:** `uv run python scripts/run_m11.py thesis --no-sec`. 0 SEC/API requests, under a minute, after the owner enters a BA thesis (v3 from the open item; v1 and v2 entered as owner notes, B, since the FY2024 10-K is not stored) and RIVN and MSTR watch theses. Expect BA 2 slips as entered and `hit` on v3's charge, RIVN hit, MSTR hit ("removed"), `hyperscaler_capex` armed (or "no confirmed spender link" if none exists — the log says).
- **Fixtures:** Boeing v1–v3 quotes, MSTR removals, the RIVN gate fail, the NVDA GM miss, the Alphabet raise.

**Part 2: Confluence (core) and size_cap**
- **Code:** `src/engine/confluence.py`, `config/confluence.toml`, `src/engine/thesis/sizing.py`.
- **Numbers:** branch `m11-part2`, migration `0048_m11_caps`, D-STO-38, D-UI-47; realized volatility `prices/vol.py` (shared with M12).
- **Tables:** `exposure_cap` (position / theme, key, max %, set by the owner).
- **Hurdle display (D32 default):** lot return − SPY total return and the CPI stretch on Portfolio, from M10 Part 1's CPI; no D13 row.
- **UI:** a confluence line (k of n, vector) on Overview; exposure by theme on Portfolio.
- **Live check:** `uv run python scripts/run_m11.py confluence --no-sec`. 0 requests, under a minute: one line per company, plus caps for the entered positions.
- **Fixtures:** MU 2023, a split case, SPCX short history, a NO_SLOWDOWN name on `f_quality`.
- **Depends on:** M04 8a (`cvd_state`, `f_quality`) and 4b-lite; the other modules' MVP builds for their votes. M11 is decided last (D31), so most votes should exist by then.

## Open risks
- Only M04 writes D13 rows today; money flow (lead) stays empty until an M02 writer exists (M05's `capex_demand` shares its input family, case 17). The vote map is proposed here, not in the other briefs.
- Theses, milestones and caps are owner-entered; names without a thesis get only M04's reasons.
- PT/ST weights are undefined in M01 (MY reused, labelled). The signal key has no thesis id (worst state shown, detail in `method`).
- Boeing v1 is secondary (B); v2's 10-K is not stored (DS7). Confirmed `spender_link` rows for `ai_infrastructure` are unchecked (data\ not readable).
- Staleness 120/10 days, the 2-spender hit, the 60-bar minimum and the `f_quality` mapping are uncalibrated starting values.

## Check notes (2026-10-13)
Cases compressed from 25 to 23 (merged, wording only). Adversarial check against the pack, the outline, DESIGN, M01, M04 (Signals out, "How M01 reads M04", notes for other modules), M02, the other MVP briefs, the migrations and `src/`.
1. **Binding — no-add gates incomplete.** The brief blocked `size_cap` only on gate fail, overdue, damage and decline. M04's table (D-M04-35, -56, -58) and D-M01-5/-6 also block tranches on AMBIGUOUS/STUMBLE, gate incomplete and not applicable. Split into exit-warning set (M01 rule 4) and no-add set (rules 1 and 3); CvD missing reads "blocked", not pass.
2. **Binding — R1 missing.** M06's MVP `moat_gate` (R1, A3) was not read. Added as a first-entry block, subject to Q06.5.
3. **Binding — M01 rule 6.** Kill hits were "shown on the page only", but rule 6 needs killswitch alerts to surface at once. Added the end-of-run alert box and a Portfolio banner; there is still no review kind.
4. **Binding — rule-4 items re-asked.** Q11.6a listed M01 rule-4 reasons as if they were open. Q11.6 now asks only about the extra triggers.
5. **Outline / overlap — "ban on AI".** M10's MVP plans `policy_event_exposure` as an M11 input. It is now a Q11.6a trigger (once M10 is built), not deferred to "until M10 reads policy feeds".
6. **Overlap — hurdle inputs.** SPY (M09 Q09.6) and CPI/M2 (M10, keyless FRED) are in other briefs. "Needs a FRED key" and "SPY, CPI: new gap" were corrected. "Understand why" 4 is noted as M10's `move_context`.
7. **Overlap — vote map.** The brief said each module's brief names its vote; none does (grep of docs/mvp). Q11.4a now proposes a starting map from the briefs' signals. M04's vote now covers NO_SLOWDOWN through `f_quality` (D-M04-53, -59), because `cvd_state` alone gives no reading for non-slowdown names. M10 has no vote (info, Q10.8a). The MU example is renamed to these signals, with "3 of 7" because M03 is low tier.
8. **Outline / M01 rule 1.** No entry threshold was mentioned. It is now stated as "none in the MVP" (Q11.4a, Deferred). `lot_status` and lot awareness are shown on Portfolio.
9. **D13 encoding.** Confluence `none` was a text value; per D-M04-9 it is now a missing row. The `size_cap` grade is weakest-input (B when owner-entered lots bind). The `exit_warning` grade/firing rule is separated. A shared theme key is written on each linked cik.
10. **Data reality.**
    - `guidance_outcome` is 0030/0031, not 0009/0013. The `guidance` rebuilds are listed.
    - Old case 5 (now 4) used outcome values that do not exist. It now uses the real ones: hit, miss, pending, removed, expired, dropped, unscored, missing.
    - `decision` has no cik/thesis/criterion column and `position.cik` is nullable; both are now listed as gaps for M11's migration.
    - DS2 is built (`unit_metric`), so KPI milestones can be code-scored for Tesla.
    - The quote-check functions are named. `split_factor` is confirmed in `price_bar`.
11. **Numbers.**
    - RIVN 5,310 ÷ 962 is the Part 4a fixture. The real DB shows a fail without that figure, so it is relabelled.
    - The MSTR result is now stated as an `exit_warning` hit.
    - Boeing v2's FY2024 10-K is not stored (latest 10-K only; DS7). The live check now expects v1/v2 as owner entries.
    - All other figures trace to the pack, M04_BUILD_LOG (Part 1b and 4a re-runs, Part 8a MU expected value) or PROBE_RESULTS (BA Z 1.53).
12. **Scorer basis.** Case 6 and Deferred now say that the shared scorer uses the latest guide (D-M04-10). The pack's "first guide" (2.1a) is a tuning item, not silently assumed.
13. **Shared capex spenders.** Q11.7a now names confirmed `spender_link` rows (D-M02-19). Whether they exist is an open risk.
14. **MVP discipline:** 4 signals, 8 questions, 2 parts and 0-request live checks were already met; no change. Length: about 19k characters before these notes, above the 15k target. The added length comes from the binding-gate, vote-map and overlap fixes. The cases list was compressed to make room.

## Refresh notes (2026-10-25, sitting 5)
- The vote map uses the lines confirmed in sittings 1–4:
  - M07 `insider_buy`;
  - M05's built vote line, plus `commitment_cover` for fabless and outsourced channels;
  - M06 `moat_verdict`;
  - M03 at medium (D-M01-8);
  - M08 `est_revision`;
  - M10 and M09 have no vote.
- The confluence example now uses real rows from the module logs (MU +1.00 "3 of 7", RIVN −0.50 "2 of 7", NVDA "0 of 7" with a `guidance_removed` exit trigger). The 2023 MU example is kept and labelled.
- New D32 section and a new Q11.9 (QP.2a money-flow writer).
- The hurdle moves from deferred to a Part 2 display line (default), now that SPY and CPI are in hand.
- Numbers from MVP_PLAN.
- Finding: all 17 active names read NO_SLOWDOWN on the 2026-10-13 log, so M04's vote is `f_quality` for every name today (D32 flag 1).
