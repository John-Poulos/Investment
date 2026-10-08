# M02 — Investment area & money flow (theme discovery)

Status: design questions answered 2026-10-07; build after M00 search + grounded LLM · Updated: 2026-10-07 · Outline headings: Select the investment area; Follow the money; Identify capex recipients · Depends on: M00 (data, storage, search/LLM) · Sources: S16, S24, S44

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

## Failure modes (to expand at build)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Phrase counts | Exhibits and boilerplate inflate document counts | Count distinct filings and companies (D-SEC-14) |
| Phrase counts | A theme renamed (e.g. new acronym) looks like a decline | Theme = phrase set; engine proposes synonyms for review |
| Breadth | Many small filers mentioning a buzzword | Breadth by industry and size; money-flow component alongside |
| News | Press-release hype vs substance | Grade A/B shown; filings carry more weight than news |

## Open questions (ask at build, D7)
- Initial seed themes and their phrases (candidates from the watchlist: AI infrastructure, HBM / advanced packaging, data-center power, space launch, quantum computing, robotics).
- Phase 2 trade-press feed list per theme.
- Digest format and where it is read (report file, UI panel).
- Promotion rules from tracked to full watchlist beyond owner click (none for now).
