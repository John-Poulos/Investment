# M02 — Investment area & money flow (theme discovery)

Status: not started — context captured · Updated: 2026-10-06 · Outline headings: Select the investment area; Follow the money; Identify capex recipients · Depends on: M00 (data, storage, search/LLM) · Sources: S16, S24, S44

## Purpose
Spot emerging themes in filings and news, follow the money (who spends, who receives), and suggest themes and candidate companies for the owner to accept or reject.

## Decisions so far
- Engine discovers themes in filings and news and makes suggestions; owner decides (D23).
- Reuse owner's retrieval code via M00 (D4).
- LLM only on stored, verified passages (D21).
- Leading filing data: RPO, purchase obligations, ≥10% customers (A1).
- Every fact carries an evidence grade (D14).

## Inputs already planned
- Phrase counts over time across all filers (M00_SEARCH Tier 1).
- Local corpus of watchlist and peer filings (Tier 2).
- Customer–supplier links from ≥10% customer disclosures; customers' news leads suppliers' prices (S44).
- Hyperscaler capex from XBRL and earnings releases.

## Open questions (ask before designing, D7)
- What counts as a theme: owner-seeded list, engine-proposed, or both?
- Which free news sources?
- How suggestions are scored (novelty, growth in mentions, money flow) and how often they are made.
- How accepted suggestions enter the watchlist.
