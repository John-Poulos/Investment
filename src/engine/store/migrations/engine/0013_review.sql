-- Review queue actions (M00_UI step 4, D-UI-12): who resolved an item and their note (U3);
-- guidance rows may be entered by the owner from an unparsed sentence (source 'owner').
-- SQLite cannot alter a CHECK constraint, so guidance is rebuilt with its rows kept.

ALTER TABLE review_queue ADD COLUMN resolved_by TEXT;
ALTER TABLE review_queue ADD COLUMN note TEXT;

CREATE TABLE guidance_new (
    guidance_id    INTEGER PRIMARY KEY,
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    accession      TEXT NOT NULL,
    filename       TEXT NOT NULL,
    metric         TEXT NOT NULL,
    basis          TEXT NOT NULL CHECK (basis IN ('GAAP', 'non-GAAP', 'unspecified')),
    period         TEXT NOT NULL,
    unit           TEXT NOT NULL CHECK (unit IN ('USD', '%', 'count')),
    kind           TEXT NOT NULL CHECK (kind IN ('range', 'plusminus', 'approx', 'point')),
    low            NUMERIC NOT NULL,
    high           NUMERIC NOT NULL,
    point          NUMERIC,
    spread         NUMERIC,
    spread_kind    TEXT CHECK (spread_kind IN ('abs', 'pct', 'bps')),
    prior_low      NUMERIC,
    prior_high     NUMERIC,
    stated_on      TEXT NOT NULL,
    source         TEXT NOT NULL CHECK (source IN ('sentence', 'table', 'owner')),
    quote          TEXT NOT NULL,
    quote_start    INTEGER NOT NULL,
    quote_end      INTEGER NOT NULL,
    period_quote   TEXT NOT NULL,
    period_start   INTEGER NOT NULL,
    period_end     INTEGER NOT NULL,
    doc_sha256     TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    extraction_id  INTEGER REFERENCES extraction (extraction_id),
    status         TEXT NOT NULL DEFAULT 'open',
    created_at     TEXT NOT NULL,
    flag           TEXT CHECK (flag IN ('not_meaningful')),
    flag_reason    TEXT,
    UNIQUE (accession, filename, metric, basis, period)
);

INSERT INTO guidance_new SELECT
    guidance_id, cik, accession, filename, metric, basis, period, unit, kind, low, high, point,
    spread, spread_kind, prior_low, prior_high, stated_on, source, quote, quote_start, quote_end,
    period_quote, period_start, period_end, doc_sha256, parser_version, extraction_id, status,
    created_at, flag, flag_reason
FROM guidance;

DROP TABLE guidance;
ALTER TABLE guidance_new RENAME TO guidance;
CREATE INDEX guidance_cik_metric ON guidance (cik, metric, period);
