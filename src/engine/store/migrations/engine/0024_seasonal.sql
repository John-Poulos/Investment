-- M02 part 6: seasonal pass (D-M02-8, -10, -14, -15, -49…52).
-- A season is keyed by its date (2026-08 = the pass due on 19 Aug 2026); its windows are
-- fixed by the key, so a late or resumed run tests the same thing (D-M02-51).

CREATE TABLE seasonal_run (
    season       TEXT PRIMARY KEY,      -- YYYY-MM of the season date
    season_date  TEXT NOT NULL,
    family       TEXT NOT NULL,         -- EFTS form family tested (10-K or 10-Q)
    latest_start TEXT NOT NULL,
    latest_end   TEXT NOT NULL,
    prior_start  TEXT NOT NULL,
    prior_end    TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('mined', 'testing', 'done')),
    detail       TEXT,                  -- JSON counts per stage, budget stops
    started_at   TEXT NOT NULL,
    finished_at  TEXT
);

-- One row per phrase per season: candidate (mined, Gemini variant or calibration) →
-- screened (page 1 passed) or screened_out → passed or failed (full test) → proposed
-- (queued for review, ≤ 10 per pass) or listed (Themes page only).
CREATE TABLE seasonal_phrase (
    season           TEXT NOT NULL,
    phrase           TEXT NOT NULL,     -- lowercase, unquoted
    source           TEXT NOT NULL CHECK (source IN ('mined', 'llm', 'calibration')),
    adopters         INTEGER,           -- watchlist companies newly using it (mined)
    droppers         INTEGER,
    adopter_ciks     TEXT,              -- JSON list
    rank             INTEGER,
    stage            TEXT NOT NULL CHECK (stage IN ('candidate', 'screened', 'screened_out',
                                                    'failed', 'passed', 'proposed', 'listed')),
    reason           TEXT,
    latest_companies INTEGER,
    prior_companies  INTEGER,
    lower_bound      INTEGER NOT NULL DEFAULT 0 CHECK (lower_bound IN (0, 1)),
    latest_docs      INTEGER,
    prior_docs       INTEGER,
    p_value          REAL,
    p0               REAL,
    growth_pts       REAL,              -- share of filers, latest − prior, in points
    spread           TEXT,              -- JSON (groups, finance, blank checks, unknown)
    crowding         TEXT,              -- JSON (fund filings latest/prior, flag)
    theme_id         INTEGER REFERENCES theme (theme_id),
    overlap          REAL,              -- share of its corpus passages naming that theme
    samples          TEXT,              -- JSON list of corpus passages
    gemini           TEXT,              -- JSON: suggested name and variants (use case 4)
    discovered_at    TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (season, phrase)
);
CREATE INDEX seasonal_phrase_stage ON seasonal_phrase (season, stage);

-- Resume state: one EFTS count per (season, phrase, family, window, page cap).
CREATE TABLE seasonal_count (
    season      TEXT NOT NULL,
    phrase      TEXT NOT NULL,
    family      TEXT NOT NULL,          -- 10-K, 10-Q or 'fund' (N-1A + 485APOS)
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL,
    max_pages   INTEGER NOT NULL,
    documents   INTEGER,                -- NULL = failed (missing, never zero)
    filings     INTEGER,
    companies   INTEGER,
    lower_bound INTEGER NOT NULL CHECK (lower_bound IN (0, 1)),
    sics        TEXT,                   -- JSON {cik: first SIC or null} of fetched hits
    error       TEXT,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (season, phrase, family, start_date, end_date, max_pages)
);

-- Companies outside the watchlist/tracked tiers that mention an active theme: candidates
-- (a substantive mention) or the watch tier (mention only), with first-mention flags.
CREATE TABLE seasonal_company (
    season        TEXT NOT NULL,
    cik           TEXT NOT NULL CHECK (length(cik) = 10),
    theme_id      INTEGER NOT NULL REFERENCES theme (theme_id),
    name          TEXT,
    ticker        TEXT,
    phrases       TEXT NOT NULL,        -- JSON list of theme phrases hit
    first_mention TEXT,                 -- earliest stored hit for the theme's phrases
    tier          TEXT NOT NULL CHECK (tier IN ('candidate', 'watch', 'unread')),
    section       TEXT,                 -- where the best mention sits
    quantified    INTEGER CHECK (quantified IN (0, 1)),
    quote         TEXT,
    accession     TEXT,
    filename      TEXT,
    quote_start   INTEGER,
    quote_end     INTEGER,
    flags         TEXT,                 -- JSON list of first-mention flags
    float_usd     NUMERIC,
    float_as_of   TEXT,
    float_ref     TEXT,                 -- accession of the 10-K cover
    size_label    TEXT,
    detail        TEXT,
    discovered_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (season, cik, theme_id)
);
