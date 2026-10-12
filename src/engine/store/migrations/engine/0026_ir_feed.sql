-- M02 part 7a: IR feed discovery (D-M02-59). Feeds found automatically for companies with
-- no entry in config/news.toml; polled only once the owner confirms them. One row per
-- company: the feed found (proposed / confirmed / rejected) or 'none_found', re-checked
-- every 90 days.

CREATE TABLE ir_feed (
    cik        TEXT PRIMARY KEY CHECK (length(cik) = 10),
    ticker     TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('proposed', 'confirmed', 'rejected', 'none_found')),
    url        TEXT,                    -- NULL when none found
    title      TEXT,                    -- the feed's own title
    domain     TEXT,                    -- company web domain the check used
    samples    TEXT,                    -- JSON list of the latest headlines
    tried      INTEGER,                 -- feed addresses tried on the last check
    detail     TEXT,
    found_at   TEXT,
    checked_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT
);
