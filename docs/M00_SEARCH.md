# M00 — Search & grounded LLM

Status: proposed (P9) · Updated: 2026-10-06 · Serves: M02, M04, M07, M11 · Sources: S24, S47, S54, S56

## Purpose
Search whole filings and news; let an LLM work only on retrieved, stored passages, with every claim mechanically checked.

## No text limits (D22)
Documents are stored and indexed whole; character limits exist only for display. The old code cut analysis text in 13 places (e.g. first 20k + last 60k chars per filing; 14k chars of LLM input).

## Tier 1 — market-wide discovery (EDGAR full-text search)
- Which filers mention a phrase, all companies since 2001; hit counts by date window = trend signal (M02).
- Limits: ≤ 10,000 hits per query; no matched text returned (fetch the document); one quoted phrase per query; OR groups unreliable.

## Tier 2 — local deep search (SQLite FTS5 in corpus.db)
- Documents split into sections (10-K Items 1, 1A, 7, 7A, 8; 10-Q parts; 8-K items; exhibits) with character offsets.
- FTS5: exact phrases, prefix, boolean, NEAR proximity, column filters, BM25 ranking, snippet/highlight, porter stemming.
- Section text stored once; FTS5 table self-contained if external-content naming would break snippet()/highlight().
- Tier 2 results are the only material the LLM may see.

## Tier 3 — semantic search (later, optional)
Embeddings to catch the same idea in different words for theme spotting. Evaluate after Tier 2 works.

## Grounded LLM pipeline (D21)
1. Retrieve passages (Tier 2); each has `passage_id`, document, section, offsets.
2. LLM returns structured items, each with a verbatim `quote` and `passage_id`.
3. Verifier (code): quote exists in that passage (whitespace-normalized); every number and unit in the item appears in the quote; period present.
4. Pass → `extraction` table with model, prompt version, verification result. Fail → review queue; never stored as fact.
5. Financial numbers come from XBRL, never the LLM. LLM handles text-only items: guidance (R19), themes (M02), customer mentions (M04).
6. Interpretations are labeled and always shown with their passages.
Model-agnostic; prompts versioned.

## Failure modes
| Risk | Guard |
|---|---|
| LLM invents a fact | Verifier rejects quotes/numbers not in the cited passage |
| Correct quote, wrong reading | Labeled as interpretation; owner review before it drives a signal |
| Section splitter misses a heading | Fall back to whole-document passages; log failures per form |
| Tokenizer splits domain terms ("HBM3E", "10b5-1") | Test queries for domain terms; add trigram index if needed |

## Decisions
- D-SRCH-1 (2026-10-06): No character limits on analysis text (owner).
- D-SRCH-2 (2026-10-06): LLM only on curated, stored data; outputs grounded in sourced passages (owner).

## Open questions
- LLM provider and cost — decide at the R19 build.
- Free news feeds for M02 (semis, AI infrastructure, energy, robotics).
