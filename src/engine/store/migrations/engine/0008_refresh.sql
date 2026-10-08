-- Nightly refresh bookkeeping (D-SEC-15): one row per run, one row per daily index day.

CREATE TABLE refresh_run (
    run_id      INTEGER PRIMARY KEY,
    trigger     TEXT NOT NULL,         -- scheduled, missed-run prompt, manual
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL CHECK (status IN ('running', 'ok', 'partial', 'failed')),
    days        TEXT,                  -- JSON list of index days read
    companies   INTEGER,
    report      TEXT,                  -- JSON summary (also written to logs/)
    error       TEXT
);

CREATE TABLE refresh_day (
    day          TEXT PRIMARY KEY,     -- YYYY-MM-DD
    status       TEXT NOT NULL CHECK (status IN ('processed', 'no_index', 'pending')),
    entries      INTEGER,              -- rows in the daily index
    matched      INTEGER,              -- rows for watchlist companies
    run_id       INTEGER REFERENCES refresh_run (run_id),
    processed_at TEXT NOT NULL
);
