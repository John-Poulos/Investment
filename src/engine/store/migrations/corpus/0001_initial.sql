-- corpus.db, initial schema (M00_STORAGE.md, M00_SEARCH.md). Rebuildable from SEC.

CREATE TABLE schema_version (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

-- Raw HTTP cache keyed by URL + sorted params. Failures are never stored.
CREATE TABLE http_cache (
    cache_key    TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    status       INTEGER NOT NULL,
    content_type TEXT,
    body         BLOB NOT NULL,
    outcome      TEXT NOT NULL CHECK (outcome IN ('ok', 'empty')),
    fetched_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL
);

-- Whole documents, untruncated (D22).
CREATE TABLE document (
    doc_id       INTEGER PRIMARY KEY,
    accession    TEXT NOT NULL,
    cik          TEXT NOT NULL CHECK (length(cik) = 10),
    filename     TEXT NOT NULL,
    doc_type     TEXT,                -- e.g. 10-K, EX-99.1
    url          TEXT NOT NULL UNIQUE,
    content_type TEXT,
    text         TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    UNIQUE (accession, filename)
);

-- Sections are offsets into document.text; the searchable copy lives in section_fts
-- (self-contained, so snippet() and highlight() work). section_id = section_fts rowid.
CREATE TABLE section (
    section_id   INTEGER PRIMARY KEY,
    doc_id       INTEGER NOT NULL REFERENCES document (doc_id) ON DELETE CASCADE,
    label        TEXT NOT NULL,       -- e.g. 10-K Item 7, 8-K Item 2.02, whole
    start_offset INTEGER NOT NULL,
    end_offset   INTEGER NOT NULL CHECK (end_offset >= start_offset)
);
CREATE INDEX section_doc ON section (doc_id);

CREATE VIRTUAL TABLE section_fts USING fts5 (
    label,
    body,
    tokenize = 'porter unicode61'
);
