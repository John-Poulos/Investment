-- EDGAR full-text search results (M00_SEARCH Tier 1, D-SEC-14): one row per query
-- run (counts kept over time for M02 trends) and the filings it matched.

CREATE TABLE fulltext_query (
    query_id   INTEGER PRIMARY KEY,
    phrase     TEXT NOT NULL,
    variant    TEXT NOT NULL CHECK (variant IN ('phrase', 'terms (fallback)')),
    forms      TEXT NOT NULL,          -- comma-separated, as sent
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    total      INTEGER NOT NULL,
    capped     INTEGER NOT NULL CHECK (capped IN (0, 1)),   -- EFTS reports at most 10,000
    hits_kept  INTEGER NOT NULL,
    sic_filter TEXT,                   -- JSON list, NULL = none
    fetched_at TEXT NOT NULL
);
CREATE INDEX fulltext_query_phrase ON fulltext_query (phrase, start_date, end_date);

CREATE TABLE fulltext_hit (
    query_id    INTEGER NOT NULL REFERENCES fulltext_query (query_id) ON DELETE CASCADE,
    accession   TEXT NOT NULL,
    filename    TEXT NOT NULL,
    cik         TEXT,
    entity_name TEXT,
    form        TEXT,
    file_date   TEXT,
    period_end  TEXT,
    sics        TEXT,                  -- JSON list
    PRIMARY KEY (query_id, accession, filename)
);
CREATE INDEX fulltext_hit_cik ON fulltext_hit (cik, file_date);
