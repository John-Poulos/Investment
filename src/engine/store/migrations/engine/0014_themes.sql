-- M02 theme core (M02_THEMES D-M02-1, D-M02-14, D-M02-15, D-M02-16).
-- Seeds come from config/themes.toml; engine proposals arrive later (part 6).
-- Every theme, phrase and company link keeps its discovery date (point-in-time backtests).

CREATE TABLE theme (
    theme_id      INTEGER PRIMARY KEY,
    key           TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    source        TEXT NOT NULL CHECK (source IN ('seed', 'engine', 'owner')),
    status        TEXT NOT NULL CHECK (status IN ('active', 'proposed', 'rejected', 'archived')),
    discovered_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE theme_phrase (
    phrase_id     INTEGER PRIMARY KEY,
    theme_id      INTEGER NOT NULL REFERENCES theme (theme_id),
    phrase        TEXT NOT NULL,      -- normalized, quoted as sent to EFTS
    source        TEXT NOT NULL CHECK (source IN ('seed', 'mined', 'llm', 'owner')),
    status        TEXT NOT NULL CHECK (status IN ('active', 'proposed', 'rejected', 'archived')),
    discovered_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (theme_id, phrase)
);

CREATE TABLE theme_company (
    theme_id      INTEGER NOT NULL REFERENCES theme (theme_id),
    ticker        TEXT NOT NULL,
    source        TEXT NOT NULL CHECK (source IN ('seed', 'engine', 'owner')),
    status        TEXT NOT NULL CHECK (status IN ('active', 'proposed', 'rejected', 'archived')),
    reason        TEXT,
    discovered_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (theme_id, ticker)
);

-- Denominator: every filing of the tracked form families, from EDGAR's quarterly
-- form index, so distinct filers per window are exact (D-M02-14).
CREATE TABLE form_filing (
    accession TEXT NOT NULL,
    cik       TEXT NOT NULL CHECK (length(cik) = 10),  -- co-registrants listed once each
    family    TEXT NOT NULL,          -- 10-K, 10-Q, 8-K, 20-F
    form      TEXT NOT NULL,          -- as listed, e.g. 10-K/A
    filed     TEXT NOT NULL,
    PRIMARY KEY (accession, cik)
);
CREATE INDEX form_filing_window ON form_filing (family, filed, cik);

CREATE TABLE form_index (
    year       INTEGER NOT NULL,
    quarter    INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    rows       INTEGER NOT NULL,      -- filings kept (tracked families only)
    last_filed TEXT,                  -- latest date in the index (data through)
    closed     INTEGER NOT NULL CHECK (closed IN (0, 1)),  -- quarter over when fetched
    source_ref TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (year, quarter)
);

-- Breadth per phrase (phrase = '' for the theme's union of phrases) per form family
-- per window. Counts are exact unless lower_bound = 1 ("≥"); NULL = missing (failed).
CREATE TABLE theme_breadth (
    theme_id    INTEGER NOT NULL REFERENCES theme (theme_id),
    phrase      TEXT NOT NULL,
    family      TEXT NOT NULL,
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL,
    documents   INTEGER,              -- EFTS total (documents, not filings)
    filings     INTEGER,
    companies   INTEGER,
    lower_bound INTEGER NOT NULL CHECK (lower_bound IN (0, 1)),
    capped      INTEGER NOT NULL CHECK (capped IN (0, 1)),   -- EFTS 10,000 cap
    filers      INTEGER,              -- denominator: distinct filers of the family
    error       TEXT,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (theme_id, phrase, family, start_date, end_date)
);
