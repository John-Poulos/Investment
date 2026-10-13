# Investment Engine — Design (running)

Updated 2026-10-12 · Basis: investment_strategy.txt (a guideline, not a spec) · Outputs are research signals, not financial or tax advice.

## Resume here
- **Phase (2026-10-13):** 4 — M02 complete (PRs #16–#30). **M04 design complete** (PR #31; D-M04-1…85 in `docs/M04_FINANCIALS.md`, D-M01-5/-6 in M01; review material in `docs/m04_review/`). **M04 build:** Parts 0, 1a, 1b, 1c, 2, 3, 7a, 4a, 6, 4b-lite, 8a merged (PRs #32–#46; MVP core complete; 5, 7b, 8b deferred). **M07 Part 1** (PR #48) and **M09 Part 1** (PR #47) built and live-checked; migrations engine 0001–0040. Setup batch: 7 plain-mature stages confirmed, 8 `m04_stage` items still open on the setup page (BA, INFQ, INTC, MU, NVDA, SPCX, TSLA, RIVN); peers confirmed for GFS, INTC, MRVL, MU, NVDA, TSLA, SPCX, AAPL (empty) — AMZN, BA, GOOG, INFQ, META, MSFT, MSTR still open, the owner may confirm later and re-run `peers`). Owner's blind labels done in `config/m04_labels.toml` (28 CvD episodes, 10 of 12 red-flag rows, with dates; research aid `docs/m04_review/LABEL_SHEETS.md`). RIVN promoted (D-M04-81). **MVP path chosen (D31, owner 2026-10-13).**
- **Next action:** **Sitting 2 — M08 valuation + M05 capex** (High effort; `docs/mvp/M08_MVP_BRIEF.md`, `M05_MVP_BRIEF.md`; plan `docs/mvp/MVP_PLAN.md`), then wave W3 = M07 Part 2 (followed-manager 13F) + M09 Part 2 (Technicals tab, price-band overlay; 6-K earnings as news; 8a reads `m01_rules`) — W3 needs no sitting and can start now; then W4 (M08 Part 1 + M05 Part 1) after sitting 2. Sittings 3 (M03 + M06), 4 (M10), 5 (M11); M12 after the MVP. Owner setup still open: 8 `m04_stage` items (BA, INFQ, INTC, MU, NVDA, SPCX, TSLA, RIVN) and 7 peer sets (AMZN, BA, GOOG, INFQ, META, MSFT, MSTR); MU's peers include WDC + Samsung/SK hynix (non-SEC) beside logic names — untick those for a memory-cycle reading (M04 build log Part 8a re-run). Rule: the main checkout stays on `main` (or the part in its live check) overnight — the refresh runs whatever is checked out (2026-10-13 incident). Open: MSFT FY2026 Q4 capex miss (Part 1b); NXP/Amkor/Ford/Oshkosh June-quarter facts (Part 2); NVDA marketable securities untagged since 2026-01 (Part 4a); TIGO ENERGY struck by the owner; DS18 short interest readable on Massive (build at tuning).
  - Sitting 1 answered (D-M07-1…8, D-M09-1…8; QP.1–3). Wave W1 (M04 4b-lite + 8a) and W2 (M07 Part 1 + M09 Part 1) done 2026-10-13.
- **Status of the real DB:** `data\engine.db` / `corpus.db`: full backfill of the 16-company watchlist (Form 4s 3 yrs, latest 10-K/10-Q, last 4 earnings 8-Ks, XBRL facts, events); 53 earnings releases scanned into the guidance ledger (guidance-4: 31 parsed, 20 none, 2 review); Meta guidance reasons from Gemini (6/6 verified, $0.0019); daily prices for all 16 tickers from Tiingo (backfill 2026-10-08, e.g. BA from 1962, SPCX from 2026-06-12). Nightly 02:00 task runs SEC refresh then Tiingo prices; logon task asks before a missed catch-up. **The owner's PC is never on overnight**, so in practice every refresh is the logon catch-up, running in the background during the owner's session (task limit 3 h) — design every scheduled job for that (D-M02-12).
- **Environment:** repo C:\dev\Investment (.venv, uv, Python 3.14, SQLite 3.50 with FTS5); GitHub John-Poulos/Investment; `.env` holds `SEC_USER_AGENT`, `GEMINI_API_KEY`, `TIINGO_API_KEY`, `ALPHA_VANTAGE_API_KEY`, `FINNHUB_API_KEY`, `MASSIVE_API_KEY`, `CONGRESS_API_KEY` (Claude may not read `.env` or `data\`; test UI changes on scratch data in the Browser pane, port 8799; stop servers only via their own background task). UI: `uv run python scripts/run_ui.py` → http://127.0.0.1:8765 (`.claude/launch.json` entry `ui`).
- **Code map:** `src/engine/sec/` client (pacing 5/s, throttle = 429 or SEC block page, `fresh=`), results (Ok/Empty/NotFound/Failed), identity (+ `entity_link`, filer category), submissions, documents, sections, xbrl_facts, asof (`facts_as_of`), cover (R1 reader), browse (browse-by-SIC), frames, insiders, events, fulltext · `src/engine/signals.py` (D13 writer, all modules) · `src/engine/financials/` shares, status, capex, trends, models (tag file), stage, queue (M04 proposals, cap 5), peers (shortlist, offsets, flags), peer_facts, stats (robust z), peer_z, profile, step, views, gate, distress, debt, gate_step, gate_view (survival gate, Part 4a), quality, estimates, special, quality_step, quality_view (Part 6) · `src/engine/ownership/` rows, classes, cards, step, views, short_interest (M07 Part 1: CMP classes, insider_buy / insider_sale / insider_net_flow, Insiders tab) · `src/engine/search/` passages, query · `src/engine/guidance/` parse, ledger, changes, calls, sources, labels, record (shared guidance scorer, M04/M11) · `src/engine/calls/` alpha_vantage, transcripts, ir_inbox, step · `src/engine/llm/` provider, verify, runs, guidance_reasons, call_check, prompts/ · `config/llm.toml` · `src/engine/ui/` app, services, viewer, settings, templates, static (vendor/ byte-exact) · `src/engine/prices/` tiingo, store · `src/engine/review.py` (review actions) · `src/engine/themes/` seeds, universe, breadth, views, tiers, proposals, industries, mining, twins, seasonal, season_pass, candidates, flags · `src/engine/store/lock.py` (refresh.lock with heartbeat) · `src/engine/moneyflow/` instance, periods, stated, actuals, guided, allocation, spenders, links, views, step · `src/engine/supply/` aliases, find, links, scan, gold, step · `src/engine/financing/` issuers, thirteenf, schedules, find, scan, links, credit, views, step · `src/engine/news/` config, fetch, items, rss, vendors, sec8k, store, match, first_mentions, discover, digest, views, step · `src/engine/official/` common, arxiv, fedreg, congress, usaspending, views, step · `src/engine/store/` db (migrations engine 0001–0037, corpus 0001–0006), http · `src/engine/refresh.py` · `scripts/` run_live.py, run_refresh.py, register_tasks.ps1, fetch_stats.py, check_tickers.py, search_check.py, guidance_samples.py, run_guidance.py, run_llm.py, run_ui.py, run_prices.py, probe_alpha_vantage.py, run_themes.py, run_calls.py, run_money.py, run_suppliers.py, run_financing.py, probe_financing.py, probe_seasonal.py, run_seasonal.py, run_news.py, run_official.py, probe_m04.py, run_financials.py, run_technicals.py, run_ownership.py · `src/engine/technicals/` params, bars (completed weeks, shared), bands (band_z, price_band, pullback_sigma; overlay history), earnings (earnings-in-window, shared), signals, step (M09 Part 1) · `src/engine/m01_rules.py` (M01 rules 1, 3, 4, 7 from M04 rows; shared) · `config/technicals.toml` · `config/themes.toml` · `config/watchlist.toml` · `config/capex_definitions.toml` · `config/aliases.toml` · `config/news.toml` · `config/company_models.toml` (M04 model tags, owner-edited) · `tests/` (629 fixture; `requests` blocked unless marked `live`) + `tests/live/` (15, opt-in).
- **Workflow:** one branch per piece → fixture tests → owner runs `uv run python scripts/run_live.py <label>` (M04 parts: `uv run python scripts/run_financials.py <subcommand>`, D-M04-69) and sends the log (Claude cannot call SEC) → PR via `gh` → owner merges with "Create a merge commit" → `git switch main`, `git pull`, `git branch -d <branch>`. Check `git branch --show-current` and `git status` before starting work. Decision IDs: D-SEC-n (M00_SEC_DATA), D-STO-n (M00_STORAGE), D-SRCH-n (M00_SEARCH).
- **Open items carried forward:** milestone dismissals → R4 tracker (M06/M11, D-UI-14) · prior-year 10-Ks for risk-factor diffs (DS7; partly, D-M04-17) · earnings-call guidance live check (DS1, D-M02-22) · Tesla delivery KPIs (DS2) · GOOG prices start 2014 (add GOOGL for longer history if wanted) · theme pass for colours (D-UI-5) · rate limiter is per process · M07 must exclude G/A/M/F from $ sale totals (R22) · Q2 (M09), Q3 (M07), Q5 (M12).
- **Awaiting owner:** review items as they arrive (`m02_tag`, `m02_capex_gap` notes, `m02_link` pairs 10/week, candidates); ORCL tracked 2026-10-09 (its earnings releases are collected once on the next refresh). Keys in `.env` (owner): `ALPHA_VANTAGE_API_KEY` (2026-10-08), `FINNHUB_API_KEY`, `MASSIVE_API_KEY`, `CONGRESS_API_KEY` (2026-10-09). Gemini model `gemini-3.1-flash-lite`, paid tier (D-SRCH-16); Tiingo free tier, internal use only (D-UI-2); Review policy: milestones and growth-rate guidance stay open for their future modules (D-UI-15).
## Working agreements
- Strategy changes are proposed with sources and applied only after owner approval (D6); ambiguous sections get questions before designs (D7).
- Each doc carries its own decisions, open items and source IDs (SOURCES.md) so a new conversation can resume without loss. Docs stay concise.
- Owner environment: Windows 11, Python, SQLite, free data sources.
- The engine produces signals and warnings; the owner makes final calls (D8, D16).

## Docs
In docs/: DESIGN.md · SOURCES.md · DATA_SOURCES.md (data needs & gaps register) · LESSONS.md (cross-module lessons, read at every build) · M04_BUILD_LOG.md (M04 build parts) · M02_BUILD_LOG.md (M02 build parts and notes) · MODULE_TEMPLATE.md · M00_SEC_DATA.md · M00_STORAGE.md · M00_SEARCH.md · M00_UI.md · M01_TIMEFRAMES.md · M02_THEMES.md · M04_FINANCIALS.md · M07_OWNERSHIP.md · M09_TECHNICALS.md · mvp/ (MVP_PLAN.md, the M0x_MVP_BRIEF.md briefs) · Repo root: CLAUDE.md (Claude Code memory; loads DESIGN.md)

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
- **D13** Signal record `{ticker, module_id, signal, value, timeframe, evidence_grade, source_ref, method, as_of}`; core computes a per-timeframe confluence score. `module_id` = which module produced the signal; `source_ref` = the document behind it. (P2) Extended by D-M04-9: enums in `value_text`, missing = a row with `method` "missing: <reason>", one row per timeframe; and by D-M04-74: `cik` on every row (ticker for display). `evidence_grade` = the weakest deciding input; `source_ref` = the newest accession, "+N" when more; the full input list in `method` (D-M04-9).
  Example: `{ticker: "XYZ", module_id: "M07", signal: "opportunistic_buy", value: 1, timeframe: "MY", evidence_grade: "A", source_ref: "Form 4 <accession no.>", method: "routine/opportunistic filter", as_of: "2026-09-12"}`
- **D14** Evidence grades: A = filing/company release, B = credible report, C = rumor. (P3) B also covers call transcripts, third-party data and owner entries without a filing (D-M04-9); daily exchange prices are A (D-M04-82).
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
| M07 | Ownership & insiders | M07_OWNERSHIP.md |
| M08 | Sentiment & valuation | — |
| M09 | Technicals | M09_TECHNICALS.md |
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
- **D27** M01 σ bands: 1–2σ triggers; depth is reported uncapped. Beyond 2σ grades stronger only when CvD = CYCLICAL_TROUGH and the survival gate passes; otherwise shown as a warning with no added strength (owner, M01 review 2026-10-07; M01 rule 7). Read per D-M01-5.
- **D28** Grounded pipeline revised (owner 2026-10-07): Python searches and extracts; Gemini runs only on request, on the refined data set, to find trends; every output carries verifiable sources to the user (M00_SEARCH D-SRCH-6…9).
- **D29** UI per M00_UI.md (owner approved 2026-10-08, was P10): local Python-rendered web app (FastAPI, Jinja2, htmx, Lightweight Charts), this PC only, shareability rules U1–U7; Tiingo free tier for daily prices. (P10)
- **D31** MVP path (owner, 2026-10-13): build every module at a basic level first (2–4 signals each, on stored data, same storage and evidence rules), then use the engine and return for tuning, calibration and the deferred parts; design packs are research, cut to an MVP brief per module and decided in one owner sitting each. M04 MVP core = Parts 0–4a, 6, 7a done + 4b-lite + 8a; 5, 7b, 8b deferred.
- **D30** M02 design per M02_THEMES.md D-M02-5…16 (owner, design review 2026-10-08/09): capex guidance positive for spender and suppliers; call guidance via Alpha Vantage, else IR documents honouring site terms (browser-download inbox); supplier evidence ladder L0–L3 first; code mines phrases, Gemini names and labels, owner confirms; capped per-item digest with crowding flag; tracked tier (toml core + promoted); tracked prices in a 3-day rotation (PC off overnight); Finnhub/Massive + IR RSS + 11 trade-press feeds + arXiv/USAspending/Federal Register/Congress.gov; 8 seed themes; build parts 1–7.

## Approved revisions for modules without docs yet
- **M03** Two S-curve types: (A) young company on its first curve; (B) established company with a new curve, tracked via segment data. (R6) Bessembinder stated as wealth creation. (R14)
- **M05** Fabless: purchase obligations/prepayments primary; capex still monitored for new offerings. (R9) Leading filing data: RPO, purchase obligations, ≥10% customers. (A1) Capex split owned by M04 (D-M04-6, amends A2; default depreciation); M05 owns growth capex × ROIC.
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
3. M02 themes — complete 2026-10-12 (parts 1–7b)
4. Remaining modules — M04 design complete 2026-10-12 (D-M04-1…83); M04 build parts 0–4a, 6, 7a merged; MVP path (D31): M04 4b-lite + 8a, MVP briefs and thin builds for M03, M05–M11 ← next

## Open questions
- **Q2** "Augmented trading range" — settled for the MVP (D-M09-8, 2026-10-13): M01's σ band is the range "we create"; a named range is chosen at tuning from a chart mock-up.
- **Q3** "CEO of equity" in the 13F note — still open after sitting 1 (D-M07-7): the owner has not identified it; the "CEO of Fidelity" (Abigail Johnson, FMR) reading is an unconfirmed guess. Added to `config/m07_managers.toml` once named.
- **Q5** Free options data coverage (chains, IV history; may need own daily IV snapshots) — check at M12.
