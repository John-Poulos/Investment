# M02 — Investment area & money flow (theme discovery)

Status: design questions answered 2026-10-07; amendments P-M02-1…8 proposed 2026-10-08 (confirm at build start) · Updated: 2026-10-08 · Outline headings: Select the investment area; Follow the money; Identify capex recipients · Depends on: M00 (data, storage, search/LLM) · Sources: S16, S24, S44

## Purpose
Spot emerging themes in filings and news, follow the money (who spends, who receives), and suggest themes and candidate companies for the owner to accept or reject.

## Decisions carried
- Engine discovers themes in filings and news and makes suggestions; owner decides (D23).
- Reuse owner's retrieval code via M00 (D4).
- LLM only on stored, verified passages (D21).
- Leading filing data: RPO, purchase obligations, ≥10% customers (A1).
- Every fact carries an evidence grade (D14).

## Inputs available (M00 built)
- Phrase counts over time across all filers, as documents, distinct filings and distinct companies per window (`fulltext.py`, D-SEC-14).
- Local corpus of watchlist and peer filings, split into sections (Tier 2, D-SRCH-4).
- XBRL capex, RPO, purchase obligations and peer statistics (`xbrl_facts`, `frames`).
- 8-K events and stored EX-99.1 press releases (`events`, `documents`).
- Customer–supplier links from ≥10% customer disclosures; customers' news leads suppliers' prices (S44) — to build.

## Decisions
- D-M02-1 (2026-10-07): A theme is a named set of phrases (one EDGAR full-text query per phrase, merged by accession) plus linked companies and money-flow links (customer capex → supplier RPO/backlog). Both sources: the owner seeds themes; the engine proposes new phrases whose distinct-filer counts rise; the owner accepts or rejects proposals (D23).
- D-M02-2 (2026-10-07): News in two phases. Phase 1, grade A only: filings, 8-K press releases, company IR RSS for watchlist and peers (owner's `ir_feeds.py` as a start). Phase 2: curated free trade-press RSS per theme, grade B. News is stored as headline, date, link and short snippet only (copyright); the LLM reads only stored passages (D21). Broad news indexes (e.g. GDELT) not planned.
- D-M02-3 (2026-10-07): Suggestions show their components side by side — growth in distinct filers vs the prior window, breadth across companies and industries, money flow (capex, RPO, purchase obligations, ≥10% customers), novelty, evidence grade — with no single combined score until backtested. Weekly scan delivered as a digest in the review queue (D8), plus a deeper pass after each 10-Q/10-K season.
- D-M02-4 (2026-10-07): Two watch tiers. An accepted candidate becomes "tracked" (filing index + XBRL facts, ~2 SEC requests); the owner promotes it to the full watchlist (Form 4s, documents, alerts; ~250 requests backfill). Both tiers are stored in the database with the theme and reason; `config/watchlist.toml` stays the owner's hand-edited core list.

## Proposed amendments (from the M00 build, 2026-10-08 — owner to confirm at M02 start)
- **P-M02-1 Forward money flow from the guidance ledger.** Capex guidance already parsed (e.g. Meta 2026 capex $130–145B, Alphabet $175–185B, Amazon ~$200B) is the spend side of "follow the money" months before XBRL capex reports it. Add it as a money-flow component (D-M02-3) beside XBRL capex/RPO, labeled guidance (grade A) with its quote link.
- **P-M02-2 Gemini roles are the approved use cases.** Theme naming/synonym proposals (D-SRCH-17 use case 4: every proposed phrase is checked against EDGAR full-text counts before the owner sees it; zero hits = shown as such) and customer/supplier links (use case 5: both names must appear in the quoted passage). Owner-initiated only, one call per theme or company, cost shown first (D-SRCH-16/18). Pattern counting, breadth and money-flow numbers stay code-only.
- **P-M02-3 Digest delivery = existing screens.** Weekly digest and proposals arrive as review-queue items (new kinds, e.g. `m02_phrase_proposal`, `m02_candidate`) with actions accept / reject / leave open, each recorded with a note (D-UI-12, D-UI-15) and explained in the review guide panel; theme detail lives in the reserved Themes tab (M00_UI). Answers the open "digest format" question if approved.
- **P-M02-4 Tracked tier in the UI.** Accepted candidates appear under "Tracked" in the side panel (already reserved) with their theme and reason; promote/demote are owner actions.
- **P-M02-5 Price budget for the tracked tier.** Nightly prices run at 75 s per symbol under 48 requests/hour and 480 symbols/month (D-UI-8). Proposal: tracked companies get prices on first open only (like peers, D-UI-3), not nightly, unless promoted to the watchlist — otherwise 50 tracked names add ~1 hour to the nightly run and eat the monthly symbol cap.
- **P-M02-6 News sources.** Phase 1 unchanged (filings, 8-K releases, company IR RSS). Candidate addition: Tiingo News API (DS4: free-tier inclusion unverified — one test call; internal use only; grade B as an aggregator). Store headline, date, link, short snippet only (D-M02-2).
- **P-M02-7 Search inputs.** Use the passage search API (D-SRCH-10) for local phrase checks and the document reader (D-UI-9) as the drill-down from any theme hit; EFTS weekly scans stay ≤ 8 requests/s with variants tagged (D-SEC-14).
- **P-M02-8 Added failure modes** (below, marked "proposed").

## Failure modes (to expand at build)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Phrase counts | Exhibits and boilerplate inflate document counts | Count distinct filings and companies (D-SEC-14) |
| Phrase counts | A theme renamed (e.g. new acronym) looks like a decline | Theme = phrase set; engine proposes synonyms for review |
| Breadth | Many small filers mentioning a buzzword | Breadth by industry and size; money-flow component alongside |
| News | Press-release hype vs substance | Grade A/B shown; filings carry more weight than news |
| LLM phrase/synonym proposals (proposed) | Plausible but unused phrases | Each proposal checked against EDGAR counts before review; zero hits shown as such |
| Capex guidance as money flow (proposed) | Guidance is a plan; it gets cut | Show as guidance with its period; compare with later XBRL capex and guidance changes (R19) |
| Tracked-tier growth (proposed) | Budget or request limits silently starve updates | Prices on open only for tracked; per-run counts on the runs/costs page |

## Open questions (ask at build, D7)
- Initial seed themes and their phrases (candidates from the watchlist: AI infrastructure, HBM / advanced packaging, data-center power, space launch, quantum computing, robotics).
- Phase 2 trade-press feed list per theme.
- Digest format and where it is read — see P-M02-3 (review queue + Themes tab).
- Promotion rules from tracked to full watchlist beyond owner click (none for now).
