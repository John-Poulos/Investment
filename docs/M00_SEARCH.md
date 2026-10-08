# M00 — Search & grounded LLM

Status: approved (D26; pipeline revised D28) · Updated: 2026-10-07 · Serves: M02, M04, M07, M11 · Sources: S24, S47, S54, S56

## Purpose
Search whole filings and news; let an LLM work only on retrieved, stored passages, with every claim mechanically checked.

## No text limits (D22)
Documents are stored and indexed whole; character limits exist only for display. The old code cut analysis text in 13 places (e.g. first 20k + last 60k chars per filing; 14k chars of LLM input).

## Tier 1 — market-wide discovery (EDGAR full-text search)
- Which filers mention a phrase, all companies since 2001; hit counts by date window = trend signal (M02).
- Limits: ≤ 10,000 hits per query; no matched text returned (fetch the document); one quoted phrase per query; OR groups unreliable.

## Tier 2 — local deep search (SQLite FTS5 in corpus.db)
- Documents split into sections (10-K Items 1, 1A, 7, 7A, 8; 10-Q parts; 8-K items; exhibits) with character offsets.
- Sections split into paragraph-aligned passages (~1.5–3k chars, offsets into the document); passages are the unit that is ranked and cited. Whole sections stay retrievable (D-SRCH-7).
- FTS5: exact phrases, prefix, boolean, NEAR proximity, column filters, BM25 ranking, snippet/highlight, porter stemming.
- Section text stored once; FTS5 table self-contained if external-content naming would break snippet()/highlight().
- Tier 2 results are the only material the LLM may see.

## Tier 3 — semantic search (later, optional)
Embeddings to catch the same idea in different words for theme spotting. Evaluate after Tier 2 works.

## Grounded pipeline (D21, revised D28)
Python searches and extracts; the LLM runs only when the owner asks, and only on the refined data set.
1. **Search (code):** FTS5 over passages; each has `passage_id`, accession, filename, section, offsets.
2. **Extract (code, versioned parser):** e.g. R19 finds outlook/guidance passages in earnings EX-99.1 and parses metric, period, low/high, unit, GAAP/non-GAAP. Each row points at its sentence by offsets, so provenance is built in. Sentences the parser cannot read go to the review queue with their passage; no LLM parse (D-SRCH-8).
3. **Ledger & scoring (code):** guidance rows stored, later scored against XBRL actuals (R19). Financial numbers come from XBRL or the parser, never the LLM.
4. **Analyze (LLM, on request only):** input = ledger rows + the passages behind them, each with an ID. Output = observations (e.g. trends across releases), each citing IDs with a verbatim quote.
5. **Verify (code):** quote exists in the cited passage (whitespace/quote-normalized); every number and unit in the observation appears in the cited passages or rows ("$1.2 billion" = 1.2e9 on both sides); a failed check rejects the observation.
6. **Store & show:** observations stored with model, prompt version, citations and verification result (D-SRCH-9); labeled as interpretation and always shown with their sources (accession link, section, quoted sentence).
Provenance survives a corpus rebuild: stored citations carry accession, filename, offsets, document sha256 and the quote, not only `passage_id`. Every LLM call logs model, prompt version, tokens and raw response. Prompts are versioned files. Fixture tests use recorded responses; live LLM calls are opt-in.

## LLM provider (D-SRCH-6)
Google Gemini via the `google-genai` SDK; key `GEMINI_API_KEY` in `.env` (owner enters it; Claude never reads it). Default model Gemini 3.1 Flash, configurable; larger Gemini models when more reasoning is needed. Code stays provider-agnostic behind one small interface.

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
- D-SRCH-3 (2026-10-07): Design approved by owner (D26, was P9).
- D-SRCH-5 (2026-10-07): Tier 1 built (`sec/fulltext.py`, D-SEC-14): phrase search with SIC post-filter and yearly/period hit counts stored over time for M02 trends; matched text is read by fetching the document (Tier 2).
- D-SRCH-4 (2026-10-07): Section splitter built (`sec/sections.py`, version items-1). Splits stored text at line-start "Item N" headings, never changing the text. 10-K headings appear in the table of contents and the body: items are taken in order and, for each, the occurrence after the previous item with the longest body wins. 10-Q labels carry the part (item numbers repeat). Sections tile the document: cover, items, signatures. Required items missing (10-K 1/7/8; 10-Q Part I 1/2; 8-K any) → one "whole" section; every outcome and what was missing goes to `split_log`, countable per form. Exhibits: one section starting after SEC's header lines. `resplit()` re-runs on stored text after a splitter change.
- D-SRCH-6 (2026-10-07): LLM provider Google Gemini (default Gemini 3.1 Flash), key `GEMINI_API_KEY` (owner).
- D-SRCH-7 (2026-10-07): Passages = paragraph-aligned chunks within sections; ranking and citations use passages. Resolves the BM25 short-section bias (owner).
- D-SRCH-8 (2026-10-07): Python does search and extraction; the LLM runs only on owner request, on the refined data set, to find trends; every output carries its sources to the user. Unparsed guidance sentences go to the review queue only (owner; D28).
- D-SRCH-9 (2026-10-07): LLM observations are stored with model, prompt version, citations and verification result (owner). First end-to-end consumer: R19 guidance (owner).
- D-SRCH-10 (2026-10-08): Passages built (`search/passages.py`, chunker para-1): lines packed greedily to ≤ 3,000 chars, tiling each section; over-long lines cut at the last sentence end after 1,500 chars, else whitespace, else hard. Built with the sections on ingest; `ensure_passages()` backfills stored documents. `search/query.py`: FTS5 query over `passage_fts` with cik / doc type / section / accession filters, BM25 with the label column (section label + title) weighted 10:1, `[` `]` snippets; `phrase()` quotes free text (needed for 10b5-1, HBM3E, $ amounts); bad syntax raises `QueryError`. `get_passage()` returns text plus accession, filename, offsets, document sha256 and parser version for citations. Live check: `scripts/search_check.py`.

## Open questions
- Exact Gemini model ID and SDK usage — check Google's docs at build.
- Free news feeds for M02 (semis, AI infrastructure, energy, robotics).
