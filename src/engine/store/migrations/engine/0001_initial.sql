-- engine.db, initial schema (M00_STORAGE.md core tables).
-- Dates are ISO-8601 text; timestamps are UTC. CIKs are 10-digit zero-padded text.
-- Missing values stay NULL, never zero.

CREATE TABLE schema_version (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE entity (
    cik                TEXT PRIMARY KEY CHECK (length(cik) = 10),
    name               TEXT NOT NULL,
    sic                TEXT,
    sic_description    TEXT,
    fiscal_year_end    TEXT,            -- MMDD as SEC reports it
    exchanges          TEXT,            -- JSON array from submissions
    tickers            TEXT,            -- JSON array from submissions
    entity_type        TEXT,
    state_of_inc       TEXT,
    source_ref         TEXT NOT NULL,
    fetched_at         TEXT NOT NULL
);

-- Ticker history: a row per (ticker, cik) span. valid_to NULL = current.
CREATE TABLE ticker (
    ticker     TEXT NOT NULL,
    cik        TEXT NOT NULL CHECK (length(cik) = 10),
    exchange   TEXT,
    name       TEXT,
    valid_from TEXT NOT NULL,
    valid_to   TEXT,
    source     TEXT NOT NULL,
    PRIMARY KEY (ticker, valid_from)
);
CREATE UNIQUE INDEX ticker_current ON ticker (ticker) WHERE valid_to IS NULL;
CREATE INDEX ticker_cik ON ticker (cik);

-- When each reference file was last refreshed (read-path freshness).
CREATE TABLE refresh_state (
    name       TEXT PRIMARY KEY,
    source_ref TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    detail     TEXT
);

-- Peers (D19): SEC filers by CIK, or non-SEC peers by name (cik NULL).
CREATE TABLE peer_group (
    group_id   INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    source     TEXT NOT NULL CHECK (source IN ('sic', 'owner', 'industry')),
    sic        TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE peer_member (
    member_id INTEGER PRIMARY KEY,
    group_id  INTEGER NOT NULL REFERENCES peer_group (group_id) ON DELETE CASCADE,
    cik       TEXT CHECK (cik IS NULL OR length(cik) = 10),
    name      TEXT NOT NULL,
    source    TEXT NOT NULL CHECK (source IN ('sic', 'owner', 'industry')),
    UNIQUE (group_id, cik),
    UNIQUE (group_id, name)
);

CREATE TABLE filing (
    accession        TEXT PRIMARY KEY,
    cik              TEXT NOT NULL CHECK (length(cik) = 10),
    form             TEXT NOT NULL,
    filed            TEXT NOT NULL,
    accepted_at      TEXT,
    report_date      TEXT,
    items            TEXT,            -- 8-K item codes, comma-separated as SEC lists them
    primary_doc      TEXT,
    primary_doc_desc TEXT,
    is_xbrl          INTEGER,
    ingested_at      TEXT NOT NULL
);
CREATE INDEX filing_cik_filed ON filing (cik, filed);
CREATE INDEX filing_form_filed ON filing (form, filed);

-- Every reported XBRL value, point-in-time (filed date kept). Instants have period_start NULL.
CREATE TABLE fact (
    fact_id      INTEGER PRIMARY KEY,
    cik          TEXT NOT NULL CHECK (length(cik) = 10),
    taxonomy     TEXT NOT NULL,
    tag          TEXT NOT NULL,
    unit         TEXT NOT NULL,
    period_start TEXT,
    period_end   TEXT NOT NULL,
    value        NUMERIC NOT NULL,
    accession    TEXT NOT NULL,
    form         TEXT,
    filed        TEXT NOT NULL,
    fy           INTEGER,
    fp           TEXT,
    frame        TEXT
);
CREATE UNIQUE INDEX fact_key
    ON fact (cik, taxonomy, tag, unit, ifnull(period_start, ''), period_end, accession);
CREATE INDEX fact_lookup ON fact (cik, tag, period_end);

-- Normalized series: first-reported and latest value per period.
CREATE TABLE series (
    cik              TEXT NOT NULL CHECK (length(cik) = 10),
    concept          TEXT NOT NULL,
    period_end       TEXT NOT NULL,
    period_type      TEXT NOT NULL,   -- e.g. Q, FY, TTM, instant
    period_start     TEXT,
    unit             TEXT NOT NULL,
    first_value      NUMERIC NOT NULL,
    first_accession  TEXT NOT NULL,
    first_filed      TEXT NOT NULL,
    latest_value     NUMERIC NOT NULL,
    latest_accession TEXT NOT NULL,
    latest_filed     TEXT NOT NULL,
    method           TEXT NOT NULL,
    parser_version   TEXT NOT NULL,
    PRIMARY KEY (cik, concept, period_end, period_type)
);

CREATE TABLE frame_value (
    taxonomy    TEXT NOT NULL,
    tag         TEXT NOT NULL,
    unit        TEXT NOT NULL,
    frame       TEXT NOT NULL,        -- e.g. CY2025Q3, CY2025Q3I
    cik         TEXT NOT NULL CHECK (length(cik) = 10),
    entity_name TEXT,
    value       NUMERIC NOT NULL,
    accession   TEXT,
    period_end  TEXT,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (taxonomy, tag, unit, frame, cik)
);

CREATE TABLE insider_txn (
    accession        TEXT NOT NULL,
    line             INTEGER NOT NULL,
    issuer_cik       TEXT NOT NULL CHECK (length(issuer_cik) = 10),
    owner_cik        TEXT,
    owner_name       TEXT,
    role             TEXT,
    table_kind       TEXT CHECK (table_kind IN ('non_derivative', 'derivative')),
    security_title   TEXT,
    txn_date         TEXT,
    code             TEXT,
    acquired_disposed TEXT CHECK (acquired_disposed IN ('A', 'D')),
    shares           NUMERIC,
    price            NUMERIC,
    shares_after     NUMERIC,
    direct_indirect  TEXT CHECK (direct_indirect IN ('D', 'I')),
    is_10b5_1        INTEGER,          -- NULL = not disclosed
    PRIMARY KEY (accession, line)
);
CREATE INDEX insider_issuer_date ON insider_txn (issuer_cik, txn_date);

-- D13 signal record.
CREATE TABLE signal (
    ticker         TEXT NOT NULL,
    module_id      TEXT NOT NULL,
    signal         TEXT NOT NULL,
    timeframe      TEXT NOT NULL CHECK (timeframe IN ('MY', 'PT', 'ST')),
    as_of          TEXT NOT NULL,
    value          NUMERIC,
    evidence_grade TEXT NOT NULL CHECK (evidence_grade IN ('A', 'B', 'C')),
    source_ref     TEXT NOT NULL,
    method         TEXT NOT NULL,
    PRIMARY KEY (ticker, module_id, signal, timeframe, as_of)
);

-- Grounded LLM items (M00_SEARCH.md). passage_id refers to corpus.db section_id.
CREATE TABLE extraction (
    extraction_id       INTEGER PRIMARY KEY,
    module_id           TEXT NOT NULL,
    item_type           TEXT NOT NULL,
    payload             TEXT NOT NULL,  -- JSON
    quote               TEXT NOT NULL,
    passage_id          INTEGER NOT NULL,
    model               TEXT NOT NULL,
    prompt_version      TEXT NOT NULL,
    verified            INTEGER NOT NULL CHECK (verified IN (0, 1)),
    verification_detail TEXT,
    created_at          TEXT NOT NULL
);

-- R19 guidance ledger.
CREATE TABLE guidance (
    guidance_id INTEGER PRIMARY KEY,
    cik         TEXT NOT NULL CHECK (length(cik) = 10),
    metric      TEXT NOT NULL,
    period      TEXT NOT NULL,
    range_low   NUMERIC,
    range_high  NUMERIC,
    unit        TEXT,
    stated_on   TEXT NOT NULL,
    source_ref  TEXT NOT NULL,
    extraction_id INTEGER REFERENCES extraction (extraction_id),
    status      TEXT NOT NULL DEFAULT 'open'
);

-- D8 owner review queue.
CREATE TABLE review_queue (
    item_id     INTEGER PRIMARY KEY,
    module_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,
    ticker      TEXT,
    cik         TEXT,
    reason      TEXT NOT NULL,
    payload     TEXT,                  -- JSON
    created_at  TEXT NOT NULL,
    resolved_at TEXT,
    resolution  TEXT
);
CREATE INDEX review_open ON review_queue (resolved_at);

-- Owner portfolio (D11, D12).
CREATE TABLE position (
    position_id       INTEGER PRIMARY KEY,
    ticker            TEXT NOT NULL,
    cik               TEXT,
    layer             TEXT NOT NULL CHECK (layer IN ('core', 'overlay')),
    profile_of_record TEXT NOT NULL CHECK (profile_of_record IN ('MY', 'PT', 'ST')),
    opened_at         TEXT NOT NULL,
    closed_at         TEXT,
    notes             TEXT
);

CREATE TABLE lot (
    lot_id        INTEGER PRIMARY KEY,
    position_id   INTEGER NOT NULL REFERENCES position (position_id),
    acquired_on   TEXT NOT NULL,
    quantity      NUMERIC NOT NULL,
    cost_per_unit NUMERIC NOT NULL,
    closed_on     TEXT,
    close_price   NUMERIC
);

CREATE TABLE decision (
    decision_id      INTEGER PRIMARY KEY,
    position_id      INTEGER REFERENCES position (position_id),
    ticker           TEXT NOT NULL,
    action           TEXT NOT NULL,
    profile          TEXT NOT NULL CHECK (profile IN ('MY', 'PT', 'ST')),
    bar_size         TEXT,
    decided_at       TEXT NOT NULL,
    rationale        TEXT,
    signal_snapshot  TEXT              -- JSON of signals shown when deciding
);

-- Every SEC call, including cache hits.
CREATE TABLE fetch_log (
    log_id     INTEGER PRIMARY KEY,
    url        TEXT NOT NULL,
    outcome    TEXT NOT NULL CHECK (outcome IN ('ok', 'empty', 'failed', 'throttled')),
    status     INTEGER,
    from_cache INTEGER NOT NULL CHECK (from_cache IN (0, 1)),
    detail     TEXT,
    at         TEXT NOT NULL
);
CREATE INDEX fetch_log_at ON fetch_log (at);
