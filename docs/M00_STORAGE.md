# M00 — Storage & refresh (SQLite)

Status: approved (D25) · Updated: 2026-10-07 · Serves: all modules · Sources: S39, S42, S48–S53

## Purpose
Hold everything the engine knows in SQLite so lookups read locally first and SEC is called only for what changed.

## Files (local disk, outside OneDrive-synced folders)
| File | Contents | Backup |
|---|---|---|
| data/engine.db | Entities, tickers, peer groups, filing index, XBRL facts, normalized series, insider trades, signals, guidance ledger, review queue, positions/lots, decisions | Nightly online backup; the one to protect |
| data/corpus.db | Documents, sections, FTS5 index, raw HTTP cache | Rebuildable from SEC |

Settings: WAL mode, `busy_timeout` 5 s, foreign keys on, `synchronous=NORMAL`. WAL needs every process on the same machine (no network drives); readers and one writer run concurrently.

## Core tables (engine.db)
| Table | Key | Notes |
|---|---|---|
| entity | cik | name, SIC, fiscal year end, exchange |
| ticker | ticker, valid_from | maps to cik; keeps ticker history |
| peer_group / peer_member | group_id, cik | source = SIC or owner (D19) |
| filing | accession | cik (first lister), form, filed, accepted_at, report_date, 8-K items, primary_doc, is_xbrl, is_inline_xbrl, size, ingested_at |
| filing_cik | accession, cik | every CIK whose submissions list the accession |
| fact | cik, taxonomy, tag, unit, start, end, accession | every reported value with filed date (point-in-time) |
| series | cik, concept, period_end, period_type | first and latest value + accessions, method, parser_version |
| frame_value | taxonomy, tag, unit, frame, cik | peer-median source |
| insider_txn | accession, line | issuer, owner, role, code, shares, price, shares_after, 10b5-1 flag |
| signal | ticker, module_id, signal, timeframe, as_of | D13 record |
| extraction | id | LLM item + quote + passage_id + verification result (M00_SEARCH.md) |
| guidance | id | R19 ledger: metric, period, range, unit, stated_on, source_ref, status |
| review_queue | id | D8 items awaiting owner |
| position / lot / decision | ids | owner portfolio, tax lots, profile of record (D12) |
| fetch_log | id | every call: url, outcome (ok/not_found/failed/throttled), detail, at |
| ticker_refresh_log | id | each ticker-map refresh: counts (stored, listed, added, changed, dropped), applied/held/forced |
| refresh_state | name | last refresh of reference files (e.g. ticker map) for read-path freshness |
| schema_version | version | ordered migrations |

## Read path (every lookup)
1. Read the stored copy with `fetched_at` and the newest filing known for that company.
2. Fresh if it reflects every known filing and is within its backstop age → serve; no SEC call.
3. Otherwise call SEC via the shared client; on `Ok`, write raw + parsed in one transaction, then serve.
4. On `Failed`, serve the stored copy flagged stale (never a blank); on `Empty`, record the checked negative.

Freshness is event-driven (SEC data changes only when a company files); backstops catch the rest.

| Data | Backstop age |
|---|---|
| Filing index (submissions) | 1 day |
| Company facts | 7 days, or immediately after a new 10-K/10-Q/8-K Item 2.02 |
| Frames (peer medians) | 30 days; refresh in earnings season |
| Documents | Never (immutable; amendments are new accessions) |
| Ticker map | 1 day |

## Refresh jobs (Windows Task Scheduler)
- **Backfill (once, or when companies are added):** per-company API calls for watchlist + peers. Bulk ZIPs only if the universe grows into the thousands (submissions.zip alone ≈ 2 GB).
- **Nightly (e.g. 02:00 ET):** daily index for prior business days → diff against stored accessions → fetch new filings for the universe → re-parse affected facts/series → index new documents → recompute signals → run report (counts, failures, throttles). Late-filed ownership forms land in the next day's index, so each run rechecks the prior day.
- Documents stored for watchlist + owner-chosen peers; other peers get facts only.

## Windows notes
- Repo and data under a local path such as `C:\dev\...`, not OneDrive-synced Documents/Desktop.
- Declare `tzdata` as a dependency (no IANA time zone database on Windows).
- No per-ticker filenames: keys live in SQLite; any file is named by CIK (reserved names like CON/PRN and colons fail on Windows).
- Open text files with `encoding="utf-8"`.
- Verified on owner's machine 2026-10-06: FTS5 present, tzdata installed. Re-run the check under uv's Python after `uv sync`.
- FTS5 check: `python -c "import sqlite3; print([r for r in sqlite3.connect(':memory:').execute('pragma compile_options') if 'FTS5' in r[0]])"` must print `('ENABLE_FTS5',)`.

## Failure modes
| Risk | Guard |
|---|---|
| Sync tool copies DB mid-write | Local path outside OneDrive |
| Writers contend | Nightly job is the only bulk writer; UI writes small transactions; busy_timeout |
| Stale data served silently | Stale flag + fetched_at shown in UI |
| Schema drift | schema_version + ordered migrations; tests migrate an empty DB |

## Decisions
- D-STO-1 (2026-10-06): SQLite (owner). Nightly incremental from the daily index replaces nightly full bulk.
- D-STO-2 (2026-10-07): Design approved by owner (D25, was P8).
- D-STO-3 (2026-10-07): Schema 0001 built (`engine/store/migrations/`). corpus.db: `document` holds full text, `section` holds offsets, `section_fts` is a self-contained FTS5 table (porter unicode61) so snippet()/highlight() work; `http_cache` holds raw responses. Instant facts have NULL period_start; uniqueness via an expression index. Each migration runs in one transaction with its schema_version row.
- D-STO-4 (2026-10-07): Migration 0002 rebuilds `fetch_log` and `http_cache` for the `not_found` outcome (D-SEC-4) and adds `ticker_refresh_log` (D-SEC-5).
- D-STO-5 (2026-10-07): Migration 0003 adds `filing_cik` and filing `is_inline_xbrl`, `size` (D-SEC-6).
- D-STO-6 (2026-10-07): corpus migration 0003 adds document `parser_version`, `encoding`, `raw_size`, `description` (D-SEC-7).

## Open questions
- Backfill universe: watchlist size and peers per group.
