# M00 — User interface

Status: approved (D29, owner 2026-10-08) · Updated: 2026-10-08 · Serves: all modules · Depends on: M00 data, storage, search, LLM · Sources: S66–S70

## Purpose
One screen to see everything the engine knows about an equity, with every number one click from its source, and one place to clear the review queue. TradingView-like layout (D3).

## Form and stack (owner choices 2026-10-08)
- Local web app opened in the browser; reachable from this PC only for now; kept shareable with a handful of people later.
- Python only: FastAPI serves pages rendered from Jinja2 templates; htmx swaps page parts without custom JavaScript; TradingView Lightweight Charts draws the chart (Apache-2.0; its attribution logo stays on, S67).
- Static assets (htmx, Lightweight Charts) kept in the repo, not loaded from a CDN: works offline, no third-party requests.
- Started with `uv run python scripts/run_ui.py` (opens the browser at http://127.0.0.1:<port>). Nightly refresh and backfill stay scheduled scripts.

## Keeping it shareable (rules from day one)
| # | Rule | Why |
|---|---|---|
| U1 | Every request resolves a *viewer* through one function; today it always returns the owner on localhost | A login replaces one function later, not every page |
| U2 | Write actions (review resolutions, Gemini runs, positions) require the owner role | Shared viewers read; only the owner spends money or changes data |
| U3 | Personal tables (positions, lots, decisions, notes, review resolutions) carry an owner id when built; reference data (filings, prices, guidance) does not | Splitting data later is a migration nightmare |
| U4 | Pages call plain Python service functions; no SQL in templates or route handlers | Same functions serve scripts, pages and a future API |
| U5 | Bind 127.0.0.1 by default; host, port and data folder come from settings; secrets stay in `.env` | Moving to a server is configuration |
| U6 | No Windows-only code in the app (the nightly scheduler is the only Windows piece) | A server runs Linux |
| U7 | Each external data feed sits behind one adapter, and its licence (personal vs display) is recorded in DATA_SOURCES.md | Sharing needs display licences; swapping a feed must not touch pages |

Before sharing (not now): login, HTTPS behind a reverse proxy, CSRF protection on forms, per-viewer Gemini budget or none, a price licence that allows display (DS8).

## Screens
### 1. Main (D3)
- **Top bar:** timeframe MY / PT / ST and bar size D / W (switch on the fly, D12; changes weights, never visibility, D10) · ticker search · review-queue count · last nightly run status with a stale flag.
- **Chart (top, ¾ width):** daily or weekly candles and volume; markers for earnings releases, other 8-K events and (with M07) insider buys/sells; hovering a marker shows its source.
- **Side panel (top, ¼):** Watchlist, then Tracked (D-M02-4). Each row: ticker, name, last close and change, badges for new filings and open review items. Clicking selects the equity.
- **Details (bottom half), tabs:**
  - *Overview:* identity, latest filings, signals (D13) once modules emit them; modules not yet built say so.
  - *Guidance (R19):* ledger by period with basis, quote link, flags; code-computed changes; stored Gemini reasons with their quotes; **Analyze** button.
  - *Financials (M04):* XBRL facts and series (data exists; red flags when M04 is built).
  - *Insiders (M07):* Form 4 transactions (data exists; classification when M07 is built).
  - *Events & filings:* 8-K events by category and severity, filing list with SEC links.
  - *Search:* Tier-2 search within this company (passages, snippets).
  - *Themes (M02):* when built.
  - *Ask (reserved):* grounded Q&A slot, not built (D-SRCH-18).

### 2. Source viewer (used everywhere)
Clicking any number, quote or snippet opens the stored passage with the quote highlighted, plus accession, form, section, filing date and a link to the document on SEC. Shows "text changed since cited" if the document hash differs from the citation.

### 3. Review queue
All open items grouped by kind, newest first, filterable by company. Each item shows its reason and source passage. Actions, all recorded with time and note:
| Kind | Actions |
|---|---|
| guidance_unparsed | Enter the guidance manually (stored as owner-entered with the same quote) · Dismiss (e.g. "milestone, not guidance") |
| guidance_conflict | Keep first · Keep other · Dismiss |
| llm_rejected | Acknowledge (rejected output never becomes fact) |
| ticker map held (D-SEC-5) | Apply · Keep stored map |
| future kinds (M02 digest, M04 ambiguous states) | Defined in their module docs |

### 4. Runs and costs
Nightly run reports, guidance scan summary, Gemini call log with tokens and cost (month to date).

## Gemini from the UI (D-SRCH-18)
- An **Analyze** button per section shows the stored result if one exists (date, model, verified/rejected counts) and a **Re-run** option.
- Starting a run shows the passages to be sent, the token count and the estimated cost, then asks for confirmation. Nothing runs automatically.
- Verified observations are shown labelled as interpretations, beside their quotes; rejected ones are shown only in the review queue.

## Display rules
1. Missing is never zero: "—" plus why (not in release, not collected, module not built, failed fetch).
2. Stale data carries its fetched date and a stale flag (M00_STORAGE read path).
3. Flagged rows (e.g. `not_meaningful`, D-SRCH-15) are greyed out with their reason.
4. No character limits on analysis text; long text is collapsed for display only (D22).
5. Units and periods are always shown (company fiscal labels, e.g. FY2027 Q3).

## Prices (DS8)
- **Personal use now:** Tiingo free tier (S68, S69): official API, 30+ years of daily history, adjusted OHLCV plus raw dividends and split factors; 50 requests/hour, 1,000/day, 500 symbols/month; **internal use only, no display to other people.**
- Storage: one `price_bar` row per symbol and day with raw OHLCV, adjusted OHLCV, dividend and split factor, source and fetch time. Backfill = one request per symbol (full history); nightly = one request per symbol for recent days, paced under 50/hour (≈ 1 per 72 s), watchlist and tracked tiers first.
- Behind one adapter (U7). **Sharing requires a display licence:** Tiingo redistribution is sold through Tiingo Sales (no public price on its pricing page; a research note of $250/month for a business plan is unverified, S70); alternatives cost more. Decide only if and when sharing happens.
- Rejected: yfinance / Stooq (unofficial, unstable, personal-use terms), Alpha Vantage free (adjusted series and full history are premium), Massive free (2 years, split-only adjustment), EODHD free (1 year), Alpaca (no redistribution, history from 2016). Details in S70.

## Build order (after approval)
1. App skeleton, rules U1–U5, main layout, side panel, Overview / Events & filings / Insiders / Financials tabs, source viewer (data already stored).
2. Prices: Tiingo adapter, `price_bar`, backfill + nightly step, chart with event markers.
3. Guidance tab with Analyze.
4. Review queue with actions.
5. Runs and costs page.

## Failure modes
| Risk | How it misleads | Guard |
|---|---|---|
| A number shown without its source | Owner trusts a misparse | Every number links to the source viewer (rule: no orphan numbers) |
| Stale prices or filings look current | Decisions on old data | Fetched date + stale flag; last run status in the top bar |
| Adjusted vs raw prices mixed | Fake gaps at splits; wrong σ bands | Chart and statistics use adjusted series; raw kept for audit |
| Unlicensed display after sharing | Licence breach | U7 + DATA_SOURCES licence column checked before any sharing |
| A click spends money | Unplanned Gemini cost | Owner-only, estimate + confirm, cached results first |
| Free-tier price limits hit | Partial chart history | Pacing under 50/hour; missing days marked missing, never filled |

## Decisions
- D-UI-1 (2026-10-08): Design approved as written (D29, was P10) (owner).
- D-UI-2 (2026-10-08): Daily prices from Tiingo free tier; key `TIINGO_API_KEY` in `.env` (owner created it; never read or logged by code). No live backup feed: a Tiingo outage leaves bars missing and flagged stale; if outages persist, swap the adapter (U7) — EODHD personal ($19.99/mo, history to 1962, personal use) is the noted fallback (S70) (owner).
- D-UI-3 (2026-10-08): Peer prices fetched when a peer is first opened, then nightly while it is on the watchlist or tracked tier (owner).
- D-UI-4 (2026-10-08): Changes during the build: a static mockup of each screen with real stored data is reviewed before that screen is built; after each build step the owner runs the app and comments; every change is recorded here as D-UI-n in the same commit as the code.
- D-UI-5 (2026-10-08): Colours are defined once as CSS variables in `ui/static/app.css`, following the system light/dark setting; a theme pass (e.g. a dark TradingView-like palette) is chosen later from a mockup and changes only that file (owner).
- D-UI-6 (2026-10-08): Build step 1 done: `engine/ui/` (settings U5, viewer U1/U2, services U4, app), `scripts/run_ui.py` (127.0.0.1:8765; `.claude/launch.json` entry `ui`). Main layout, side panel (unresolved tickers shown, never dropped), chart placeholder with earnings-release markers, tabs Overview / Financials (XBRL series, quarterly flows and balance sheet, each value linked to its filing) / Insiders (Form 4) / Events and filings / Search (Tier 2 within the company; invalid syntax retried as an exact phrase) / source viewer (cited text highlighted; warns if the document hash changed). Pages render on the server with no JavaScript yet. Guidance, Themes and Ask show their build status.

## Open questions
- Phone-sized layout: not planned while local-only.
