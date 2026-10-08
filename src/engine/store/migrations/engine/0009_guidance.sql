-- R19 guidance ledger, parsed by code from earnings releases (M00_SEARCH D-SRCH-8/11).
-- The 0001 guidance table was never written, so it is rebuilt with provenance columns:
-- each row quotes the exact sentence or table row (document offsets + text) it came from.

DROP TABLE guidance;

CREATE TABLE guidance (
    guidance_id    INTEGER PRIMARY KEY,
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    accession      TEXT NOT NULL,
    filename       TEXT NOT NULL,
    metric         TEXT NOT NULL,      -- revenue, gross_margin, eps_diluted, ...
    basis          TEXT NOT NULL CHECK (basis IN ('GAAP', 'non-GAAP', 'unspecified')),
    period         TEXT NOT NULL,      -- company fiscal label: FY2027 Q3, FY2026, FY2026 remaining
    unit           TEXT NOT NULL CHECK (unit IN ('USD', '%', 'count')),
    kind           TEXT NOT NULL CHECK (kind IN ('range', 'plusminus', 'approx', 'point')),
    low            NUMERIC NOT NULL,
    high           NUMERIC NOT NULL,
    point          NUMERIC,
    spread         NUMERIC,            -- as stated: dollars, percent or basis points
    spread_kind    TEXT CHECK (spread_kind IN ('abs', 'pct', 'bps')),
    prior_low      NUMERIC,            -- prior guidance stated in the same sentence
    prior_high     NUMERIC,
    stated_on      TEXT NOT NULL,      -- filing date of the release
    source         TEXT NOT NULL CHECK (source IN ('sentence', 'table')),
    quote          TEXT NOT NULL,      -- exact text of the sentence or table row
    quote_start    INTEGER NOT NULL,   -- offsets into corpus document.text
    quote_end      INTEGER NOT NULL,
    period_quote   TEXT NOT NULL,      -- exact text the period was read from
    period_start   INTEGER NOT NULL,
    period_end     INTEGER NOT NULL,
    doc_sha256     TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    extraction_id  INTEGER REFERENCES extraction (extraction_id),
    status         TEXT NOT NULL DEFAULT 'open',
    created_at     TEXT NOT NULL,
    UNIQUE (accession, filename, metric, basis, period)
);
CREATE INDEX guidance_cik_metric ON guidance (cik, metric, period);

-- One row per scanned release, so "no guidance in the release" is recorded, not missing.
CREATE TABLE guidance_scan (
    accession      TEXT NOT NULL,
    filename       TEXT NOT NULL,
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    filed          TEXT NOT NULL,
    outcome        TEXT NOT NULL CHECK (outcome IN ('parsed', 'none', 'review')),
    candidates     INTEGER NOT NULL,   -- guidance-like sentences seen
    items          INTEGER NOT NULL,   -- ledger rows written
    unparsed       INTEGER NOT NULL,   -- sentences sent to the review queue
    conflicts      INTEGER NOT NULL,   -- same metric/basis/period with different values
    parser_version TEXT NOT NULL,
    at             TEXT NOT NULL,
    PRIMARY KEY (accession, filename)
);
