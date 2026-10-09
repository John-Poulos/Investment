-- M02 part 4, call guidance (D-M02-6, D-M02-20, D-M02-21).
-- Guidance rows gain their origin (release / call transcript / company IR document), an
-- evidence grade (call transcripts are B until a company document states the same figure),
-- the release they were matched against, the capex "including/excluding ..." clause
-- (D-M02-5), and direction-only rows ("FY27 capex to grow": no figure, low/high NULL).
-- SQLite cannot alter CHECK constraints, so guidance is rebuilt with its rows kept.

CREATE TABLE guidance_new (
    guidance_id       INTEGER PRIMARY KEY,
    cik               TEXT NOT NULL CHECK (length(cik) = 10),
    accession         TEXT NOT NULL,
    filename          TEXT NOT NULL,
    metric            TEXT NOT NULL,
    basis             TEXT NOT NULL CHECK (basis IN ('GAAP', 'non-GAAP', 'unspecified')),
    period            TEXT NOT NULL,
    unit              TEXT NOT NULL CHECK (unit IN ('USD', '%', 'count')),
    kind              TEXT NOT NULL CHECK (kind IN ('range', 'plusminus', 'approx', 'point',
                                                    'direction')),
    low               NUMERIC,
    high              NUMERIC,
    point             NUMERIC,
    spread            NUMERIC,
    spread_kind       TEXT CHECK (spread_kind IN ('abs', 'pct', 'bps')),
    prior_low         NUMERIC,
    prior_high        NUMERIC,
    stated_on         TEXT NOT NULL,
    source            TEXT NOT NULL CHECK (source IN ('sentence', 'table', 'owner')),
    quote             TEXT NOT NULL,
    quote_start       INTEGER NOT NULL,
    quote_end         INTEGER NOT NULL,
    period_quote      TEXT NOT NULL,
    period_start      INTEGER NOT NULL,
    period_end        INTEGER NOT NULL,
    doc_sha256        TEXT NOT NULL,
    parser_version    TEXT NOT NULL,
    extraction_id     INTEGER REFERENCES extraction (extraction_id),
    status            TEXT NOT NULL DEFAULT 'open',
    created_at        TEXT NOT NULL,
    flag              TEXT CHECK (flag IN ('not_meaningful')),
    flag_reason       TEXT,
    origin            TEXT NOT NULL DEFAULT 'release' CHECK (origin IN ('release', 'call', 'ir')),
    grade             TEXT NOT NULL DEFAULT 'A' CHECK (grade IN ('A', 'B')),
    matched_accession TEXT,            -- company document stating the same figure (B → A)
    clause            TEXT,            -- "including principal payments on finance leases"
    direction         TEXT CHECK (direction IN ('up', 'down', 'flat')),
    CHECK ((kind = 'direction') = (low IS NULL AND high IS NULL AND direction IS NOT NULL)),
    UNIQUE (accession, filename, metric, basis, period)
);

INSERT INTO guidance_new (
    guidance_id, cik, accession, filename, metric, basis, period, unit, kind, low, high, point,
    spread, spread_kind, prior_low, prior_high, stated_on, source, quote, quote_start, quote_end,
    period_quote, period_start, period_end, doc_sha256, parser_version, extraction_id, status,
    created_at, flag, flag_reason)
SELECT
    guidance_id, cik, accession, filename, metric, basis, period, unit, kind, low, high, point,
    spread, spread_kind, prior_low, prior_high, stated_on, source, quote, quote_start, quote_end,
    period_quote, period_start, period_end, doc_sha256, parser_version, extraction_id, status,
    created_at, flag, flag_reason
FROM guidance;

DROP TABLE guidance;
ALTER TABLE guidance_new RENAME TO guidance;
CREATE INDEX guidance_cik_metric ON guidance (cik, metric, period);

-- Sentences that looked like guidance but were not queued (calls: only capex goes to review).
ALTER TABLE guidance_scan ADD COLUMN skipped INTEGER NOT NULL DEFAULT 0;

-- One row per call document in corpus.db (Alpha Vantage transcript or a company IR file the
-- owner downloaded). quarter = the company's fiscal label, e.g. 'FY2026 Q4'.
CREATE TABLE call_document (
    accession         TEXT NOT NULL,   -- corpus document.accession, e.g. AV-MSFT-2026Q4
    filename          TEXT NOT NULL,
    cik               TEXT NOT NULL CHECK (length(cik) = 10),
    symbol            TEXT NOT NULL,
    quarter           TEXT NOT NULL,
    source            TEXT NOT NULL CHECK (source IN ('alpha_vantage', 'ir_download')),
    doc_kind          TEXT NOT NULL,   -- transcript | prepared_remarks | cfo_commentary
    release_accession TEXT,            -- the quarter's earnings 8-K (Item 2.02), if found
    stated_on         TEXT,            -- that 8-K's filing date (the call is the same day or next)
    added_at          TEXT NOT NULL,
    PRIMARY KEY (accession, filename)
);
CREATE INDEX call_document_cik ON call_document (cik, quarter);

-- Transcript requests per (symbol, fiscal quarter): an empty reply means "not available yet"
-- and is retried daily for ~30 days, then an m02_ir_download reminder is queued.
CREATE TABLE call_fetch (
    symbol            TEXT NOT NULL,
    quarter           TEXT NOT NULL,   -- Alpha Vantage label, e.g. 2026Q4 (fiscal)
    cik               TEXT NOT NULL CHECK (length(cik) = 10),
    release_accession TEXT,
    release_filed     TEXT,
    outcome           TEXT NOT NULL CHECK (outcome IN ('ok', 'empty', 'failed')),
    attempts          INTEGER NOT NULL,
    first_at          TEXT NOT NULL,
    last_at           TEXT NOT NULL,
    detail            TEXT,
    reminder_queued   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, quarter)
);
