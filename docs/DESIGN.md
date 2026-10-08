# Investment Engine — Design (running)

Updated 2026-10-07 · Basis: investment_strategy.txt (a guideline, not a spec) · Outputs are research signals, not financial or tax advice.

## Resume here
- **Phase (2026-10-07):** 2 — M00 data layer built. PRs #1–#8 merged to main; **branch `m00-refresh` open** (nightly job + fixes D-SEC-15…18), PR to open/merge once the first backfill succeeds.
- **Next action:** M02 design questions (M02_THEMES open questions, D7) — discussed with the owner at high effort; then build **M00 search + grounded LLM** (M02 depends on it). PR #9 merged; backfill complete; SPCX confirmed = SpaceX.
- **Status of the real DB:** `data\engine.db` / `corpus.db` hold the full backfill of the 16-company watchlist (Form 4s 3 years, latest 10-K/10-Q, last 4 earnings 8-Ks, XBRL facts, events). Runs 1–3 hit bugs since fixed (D-SEC-16…18); run 4 ok. Windows tasks registered: 02:00 nightly (wakes PC), logon check asks before a missed catch-up.
- **Environment:** repo C:\dev\Investment (.venv, uv, Python 3.14, SQLite 3.50 with FTS5); GitHub John-Poulos/Investment; `.env` holds a valid `SEC_USER_AGENT` (Claude may not read `.env` or `data\`).
- **Code map:** `src/engine/sec/` client (pacing 5/s, throttle = 429 or SEC block page, `fresh=`), results (Ok/Empty/NotFound/Failed), identity, submissions, documents, sections, xbrl_facts, frames, insiders, events, fulltext · `src/engine/store/` db (migrations engine 0001–0008, corpus 0001–0004), http · `src/engine/refresh.py` · `scripts/` run_live.py, run_refresh.py, register_tasks.ps1, fetch_stats.py, check_tickers.py · `config/watchlist.toml` · `tests/` (188 fixture) + `tests/live/` (12, opt-in).
- **Workflow:** one branch per piece → fixture tests → owner runs `uv run python scripts/run_live.py <label>` and sends the log (Claude cannot call SEC) → PR via `gh` → owner merges with "Create a merge commit" → `git switch main`, `git pull`, `git branch -d <branch>`. Check `git branch --show-current` and `git status` before starting work. Decision IDs: D-SEC-n (M00_SEC_DATA), D-STO-n (M00_STORAGE), D-SRCH-n (M00_SEARCH).
- **Open items carried forward:** BM25 favours short sections (search build) · capex fallback tag must be shown to the user; separate shares concepts (M04/M07) · peer period-end offset tolerance (M04) · SIC peer discovery (D19) · Form 4 bulk data sets deferred · rate limiter is per process · EdgarTools evaluation · LLM provider and cost (R19 build) · M07 must exclude G/A/M/F from $ sale totals (R22) · M02 design questions · M04 red flags · Q2 (M09), Q3 (M07), Q5 (M12).
- **Awaiting owner:** answers to the M02 design questions.
## Working agreements
- Strategy changes are proposed with sources and applied only after owner approval (D6); ambiguous sections get questions before designs (D7).
- Each doc carries its own decisions, open items and source IDs (SOURCES.md) so a new conversation can resume without loss. Docs stay concise.
- Owner environment: Windows 11, Python, SQLite, free data sources.
- The engine produces signals and warnings; the owner makes final calls (D8, D16).

## Docs
In docs/: DESIGN.md · SOURCES.md · MODULE_TEMPLATE.md · M00_SEC_DATA.md · M00_STORAGE.md · M00_SEARCH.md · M01_TIMEFRAMES.md · M02_THEMES.md · M04_FINANCIALS.md · Repo root: CLAUDE.md (Claude Code memory; loads DESIGN.md)

## Scope and data
- **S1** v1 covers US-listed equities and options. Crypto is out of scope.
- **S2** Free sources only for now (SEC EDGAR, FRED, free market data); paid sources later.

## Decisions
- **D1** Modular: core engine + pluggable modules following the outline's headings.
- **D2** Three timeframes (MY years, PT months, ST weeks), each with per-strategy parameters. MY first.
- **D3** UI: TradingView-like. Top half: chart at 3/4 width. Side panel: equity links. Bottom half: selected-equity details.
- **D4** M02 reuses the owner's retrieval code: request it at that phase and review what fits first.
- **D5** Docs: this file + one concise file per module (MODULE_TEMPLATE.md).
- **D6** Outline changes are proposed with sources first; approved items become decisions, rejected items are deleted.
- **D7** For ambiguous sections, ask clarifying questions before proposing designs.
- **D8** Automate clear signals; ambiguous classifications go to a user review queue.
- **D9** Every indicator documents its failure modes ("how could this data mislead?") in its module doc.
- **D10** All module outputs are visible for every equity in every timeframe; profiles change weights, not visibility.
- **D11** A holding = core lots + optional overlays, each judged under its own profile.
- **D12** Timeframe = parameter profile consumed by every module. The user can switch profiles and bar sizes on the fly; each decision logs the profile it was made under, and positions keep a profile of record. (P1)
- **D13** Signal record `{ticker, module_id, signal, value, timeframe, evidence_grade, source_ref, method, as_of}`; core computes a per-timeframe confluence score. `module_id` = which module produced the signal; `source_ref` = the document behind it. (P2)
  Example: `{ticker: "XYZ", module_id: "M07", signal: "opportunistic_buy", value: 1, timeframe: "MY", evidence_grade: "A", source_ref: "Form 4 <accession no.>", method: "routine/opportunistic filter", as_of: "2026-09-12"}`
- **D14** Evidence grades: A = filing/company release, B = credible report, C = rumor. (P3)
- **D15** Module map (P4):

| ID | Module | Doc |
|---|---|---|
| M00 | Core engine + UI; SEC data, storage, search | M00_SEC_DATA.md, M00_STORAGE.md, M00_SEARCH.md |
| M01 | Timeframe profiles | M01_TIMEFRAMES.md |
| M02 | Investment area & money flow | M02_THEMES.md |
| M03 | Leaders & S-curve | — |
| M04 | Financials & red flags | M04_FINANCIALS.md |
| M05 | Capex & future spend | — |
| M06 | Moat | — |
| M07 | Ownership & insiders | — |
| M08 | Sentiment & valuation | — |
| M09 | Technicals | — |
| M10 | Macro & narrative | — |
| M11 | Thesis, sizing & killswitch | — |
| M12 | Options overlay | — |

- **D16** Exit signals are warnings only; the user makes the final call.
- **D17** Python backend reusing the owner's SEC access patterns. (P5)
- **D18** SEC data layer per M00_SEC_DATA.md; storage in SQLite. (P6)
- **D19** Peer groups from SEC industry codes, owner overrides, industry series where key peers don't file with the SEC. (R24)
- **D20** Owner develops on Windows 11; data on local disk outside synced folders.
- **D21** LLM only on curated, stored data; every output cites stored passages and is mechanically verified (M00_SEARCH.md).
- **D22** No character limits on analysis text; limits for display only.
- **D23** M02 discovers themes in filings and news and suggests them; owner decides.
- **D24** Repo and tooling per P7 (owner proceeding 2026-10-06): uv, ruff (`ruff-check` + `ruff-format`), pytest (live SEC tests opt-in via `-m live`), pre-commit with gitleaks; LF line endings, CRLF for .ps1/.bat/.cmd; `tests/fixtures/` byte-exact; CLAUDE.md loads DESIGN.md for Code-tab sessions; `.claude/settings.json` (committed) denies reading .env and data/, allows tests/lint/uv sync/read-only git, asks before git push, uv add and live SEC tests; old engine code kept read-only in `reference/old_engine/` (excluded from ruff).
- **D25** Storage & refresh per M00_STORAGE.md (owner approved 2026-10-07). (P8)
- **D26** Search & grounded LLM per M00_SEARCH.md (owner approved 2026-10-07). (P9)
- **D27** M01 σ bands: 1–2σ triggers; depth is reported uncapped. Beyond 2σ grades stronger only when CvD = CYCLICAL_TROUGH and the survival gate passes; otherwise shown as a warning with no added strength (owner, M01 review 2026-10-07; M01 rule 7).

## Approved revisions for modules without docs yet
- **M03** Two S-curve types: (A) young company on its first curve; (B) established company with a new curve, tracked via segment data. (R6) Bessembinder stated as wealth creation. (R14)
- **M05** Fabless: purchase obligations/prepayments primary; capex still monitored for new offerings. (R9) Leading filing data: RPO, purchase obligations, ≥10% customers. (A1)
- **M06** Invest only with a moat. (R1) HBM: three-supplier oligopoly at volume. (R8) Moat duration ≥ timeframe. (A3) Track named challengers: sampling → small-scale → volume → qualified at a major customer; buyer trust is read at the qualification rung. (R21)
- **M07** Weight opportunistic open-market buys; routine/10b5-1 sales are noise unless abnormal. (R7) Totals from raw Form 4s. (R13) Form 4 and 13D/G surface in all timeframes; 13F is lagged. (R16) Show sales as $, % of seller's stake, % of float/avg volume. (R22)
- **M08** PEG only when EPS > 0 and growth > 0; sales-based fallback; flag cyclicals. (R6) Use analyst revisions and dispersion, not target levels. (R15)
- **M09** Mean reversion only on fundamentally qualified names. (R3) "80% dead or dying" is a heuristic. (R17) Logic per timeframe: reversal (ST), momentum (PT), fundamentals-led (MY). (A4)
- **M11** Dated, checkable milestones separate early from wrong. (R4) Guidance ledger: score forward-looking statements against actuals; weight near-term, verifiable milestones; diff consecutive releases. (R19) Hurdle: S&P 500 TR; stretch TR + CPI. (R5) Theme and shared-killswitch exposure with user caps. (R23)
- **M12** Signals only, no enforcement: covered-call window when regime is weak/sideways, IV high vs its own history, no earnings inside the option's life. Default template 30–45 DTE, ~15 delta, labeled index-derived (single-stock options carry little volatility premium on average). Tax/assignment notes informational. (R20, modified)
- **Core** AMD–Google custom ASIC stays grade C until confirmed; AVGO–Google confirmed. (R10)

## Proposed (pending approval)
- None.

## Phases
0. Research/review — done 2026-10-06
1. M01 multi-year profile — reviewed 2026-10-07 (D27)
2. M00 SEC data + storage + search ← current; then M02
3. Remaining modules; M04 CvD approved early

## Open questions
- **Q2** "Augmented trading range" — ask at M09.
- **Q3** "CEO of equity" in the 13F note — ask at M07.
- **Q5** Free options data coverage (chains, IV history; may need own daily IV snapshots) — check at M12.
