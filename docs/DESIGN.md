# Investment Engine — Design (running)

Updated 2026-10-10 · Basis: investment_strategy.txt (a guideline, not a spec) · Outputs are research signals, not financial or tax advice.

## Resume here
- **Phase (2026-10-10):** 3 — M02 build: parts 1, 2, 3, 4 + 4b, 5 merged (PRs #16–#18, #20, #21; D-M02-17…40); financing-links design merged (PR #22, D-M02-41…44); **part 5b built on branch `m02-part5b` (D-M02-45 probe decisions, D-M02-46 build), live check pending**. M00 complete.
- **Next action:** owner runs the part-5b live check `uv run python scripts/run_financing.py` (~450 SEC requests, a few minutes) and sends logs/financing_*.txt; fix rounds on `m02-part5b` (Medium effort; read M02_BUILD_LOG.md "Part 5b — Financing links" and LESSONS.md); then PR → merge. Part 6 follows (its pre-build note is in the build log; ask its three open questions first).
- **Status of the real DB:** `data\engine.db` / `corpus.db`: full backfill of the 16-company watchlist (Form 4s 3 yrs, latest 10-K/10-Q, last 4 earnings 8-Ks, XBRL facts, events); 53 earnings releases scanned into the guidance ledger (guidance-4: 31 parsed, 20 none, 2 review); Meta guidance reasons from Gemini (6/6 verified, $0.0019); daily prices for all 16 tickers from Tiingo (backfill 2026-10-08, e.g. BA from 1962, SPCX from 2026-06-12). Nightly 02:00 task runs SEC refresh then Tiingo prices; logon task asks before a missed catch-up. **The owner's PC is never on overnight**, so in practice every refresh is the logon catch-up, running in the background during the owner's session (task limit 3 h) — design every scheduled job for that (D-M02-12).
- **Environment:** repo C:\dev\Investment (.venv, uv, Python 3.14, SQLite 3.50 with FTS5); GitHub John-Poulos/Investment; `.env` holds `SEC_USER_AGENT`, `GEMINI_API_KEY`, `TIINGO_API_KEY`, `ALPHA_VANTAGE_API_KEY`, `FINNHUB_API_KEY`, `MASSIVE_API_KEY`, `CONGRESS_API_KEY` (Claude may not read `.env` or `data\`; test UI changes on scratch data in the Browser pane, port 8799; stop servers only via their own background task). UI: `uv run python scripts/run_ui.py` → http://127.0.0.1:8765 (`.claude/launch.json` entry `ui`).
- **Code map:** `src/engine/sec/` client (pacing 5/s, throttle = 429 or SEC block page, `fresh=`), results (Ok/Empty/NotFound/Failed), identity, submissions, documents, sections, xbrl_facts, frames, insiders, events, fulltext · `src/engine/search/` passages, query · `src/engine/guidance/` parse, ledger, changes, calls, sources, labels · `src/engine/calls/` alpha_vantage, transcripts, ir_inbox, step · `src/engine/llm/` provider, verify, runs, guidance_reasons, call_check, prompts/ · `config/llm.toml` · `src/engine/ui/` app, services, viewer, settings, templates, static (vendor/ byte-exact) · `src/engine/prices/` tiingo, store · `src/engine/review.py` (review actions) · `src/engine/themes/` seeds, universe, breadth, views, tiers, proposals · `src/engine/moneyflow/` instance, periods, stated, actuals, guided, allocation, spenders, links, views, step · `src/engine/supply/` aliases, find, links, scan, gold, step · `src/engine/financing/` issuers, thirteenf, schedules, find, scan, links, credit, views, step · `src/engine/store/` db (migrations engine 0001–0023, corpus 0001–0006), http · `src/engine/refresh.py` · `scripts/` run_live.py, run_refresh.py, register_tasks.ps1, fetch_stats.py, check_tickers.py, search_check.py, guidance_samples.py, run_guidance.py, run_llm.py, run_ui.py, run_prices.py, probe_alpha_vantage.py, run_themes.py, run_calls.py, run_money.py, run_suppliers.py, run_financing.py, probe_financing.py · `config/themes.toml` · `config/watchlist.toml` · `config/capex_definitions.toml` · `config/aliases.toml` · `tests/` (443 fixture) + `tests/live/` (15, opt-in).
- **Workflow:** one branch per piece → fixture tests → owner runs `uv run python scripts/run_live.py <label>` and sends the log (Claude cannot call SEC) → PR via `gh` → owner merges with "Create a merge commit" → `git switch main`, `git pull`, `git branch -d <branch>`. Check `git branch --show-current` and `git status` before starting work. Decision IDs: D-SEC-n (M00_SEC_DATA), D-STO-n (M00_STORAGE), D-SRCH-n (M00_SEARCH).
- **Open items carried forward:** milestone dismissals → R4 tracker (M06/M11, D-UI-14) · prior-year 10-Ks for risk-factor diffs (DS7) · earnings-call guidance live check (DS1, D-M02-22) · Tesla delivery KPIs (DS2) · GOOG prices start 2014 (add GOOGL for longer history if wanted) · theme pass for colours (D-UI-5) · capex fallback tag must be shown to the user; separate shares concepts (M04/M07) · peer period-end offset tolerance (M04) · SIC peer discovery (D19) · rate limiter is per process · EdgarTools evaluation · M07 must exclude G/A/M/F from $ sale totals (R22) · M04 red flags · Q2 (M09), Q3 (M07), Q5 (M12).
- **Awaiting owner:** review items as they arrive (`m02_tag`, `m02_capex_gap` notes, `m02_link` pairs 10/week, candidates); ORCL tracked 2026-10-09 (its earnings releases are collected once on the next refresh). Keys in `.env` (owner): `ALPHA_VANTAGE_API_KEY` (2026-10-08), `FINNHUB_API_KEY`, `MASSIVE_API_KEY`, `CONGRESS_API_KEY` (2026-10-09). Gemini model `gemini-3.1-flash-lite`, paid tier (D-SRCH-16); Tiingo free tier, internal use only (D-UI-2); Review policy: milestones and growth-rate guidance stay open for their future modules (D-UI-15).
## Working agreements
- Strategy changes are proposed with sources and applied only after owner approval (D6); ambiguous sections get questions before designs (D7).
- Each doc carries its own decisions, open items and source IDs (SOURCES.md) so a new conversation can resume without loss. Docs stay concise.
- Owner environment: Windows 11, Python, SQLite, free data sources.
- The engine produces signals and warnings; the owner makes final calls (D8, D16).

## Docs
In docs/: DESIGN.md · SOURCES.md · DATA_SOURCES.md (data needs & gaps register) · LESSONS.md (cross-module lessons, read at every build) · M02_BUILD_LOG.md (M02 build parts and notes) · MODULE_TEMPLATE.md · M00_SEC_DATA.md · M00_STORAGE.md · M00_SEARCH.md · M00_UI.md · M01_TIMEFRAMES.md · M02_THEMES.md · M04_FINANCIALS.md · Repo root: CLAUDE.md (Claude Code memory; loads DESIGN.md)

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
| M00 | Core engine + UI; SEC data, storage, search | M00_SEC_DATA.md, M00_STORAGE.md, M00_SEARCH.md, M00_UI.md |
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
- **D28** Grounded pipeline revised (owner 2026-10-07): Python searches and extracts; Gemini runs only on request, on the refined data set, to find trends; every output carries verifiable sources to the user (M00_SEARCH D-SRCH-6…9).
- **D29** UI per M00_UI.md (owner approved 2026-10-08, was P10): local Python-rendered web app (FastAPI, Jinja2, htmx, Lightweight Charts), this PC only, shareability rules U1–U7; Tiingo free tier for daily prices. (P10)
- **D30** M02 design per M02_THEMES.md D-M02-5…16 (owner, design review 2026-10-08/09): capex guidance positive for spender and suppliers; call guidance via Alpha Vantage, else IR documents honouring site terms (browser-download inbox); supplier evidence ladder L0–L3 first; code mines phrases, Gemini names and labels, owner confirms; capped per-item digest with crowding flag; tracked tier (toml core + promoted); tracked prices in a 3-day rotation (PC off overnight); Finnhub/Massive + IR RSS + 11 trade-press feeds + arXiv/USAspending/Federal Register/Congress.gov; 8 seed themes; build parts 1–7.

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
- None. (P-M02-1…8 settled 2026-10-08 → D-M02-5…15, see D30.)

## Phases
0. Research/review — done 2026-10-06
1. M01 multi-year profile — reviewed 2026-10-07 (D27)
2. M00 SEC data + storage + search + UI — complete on merge of `m00-ui`
3. M02 themes — design complete 2026-10-09; build parts 1–7 ← next
4. Remaining modules; M04 CvD approved early

## Open questions
- **Q2** "Augmented trading range" — ask at M09.
- **Q3** "CEO of equity" in the 13F note — ask at M07.
- **Q5** Free options data coverage (chains, IV history; may need own daily IV snapshots) — check at M12.
