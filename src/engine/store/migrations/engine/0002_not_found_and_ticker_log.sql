-- 404 is "no file at this URL" (not_found), not a checked negative (D-SEC-4).
-- SQLite cannot alter a CHECK constraint, so fetch_log is rebuilt.

CREATE TABLE fetch_log_new (
    log_id     INTEGER PRIMARY KEY,
    url        TEXT NOT NULL,
    outcome    TEXT NOT NULL CHECK (outcome IN ('ok', 'not_found', 'failed', 'throttled')),
    status     INTEGER,
    from_cache INTEGER NOT NULL CHECK (from_cache IN (0, 1)),
    detail     TEXT,
    at         TEXT NOT NULL
);

INSERT INTO fetch_log_new (log_id, url, outcome, status, from_cache, detail, at)
SELECT log_id, url, CASE outcome WHEN 'empty' THEN 'not_found' ELSE outcome END,
       status, from_cache, detail, at
FROM fetch_log;

DROP TABLE fetch_log;
ALTER TABLE fetch_log_new RENAME TO fetch_log;
CREATE INDEX fetch_log_at ON fetch_log (at);

-- One row per ticker-map refresh, applied or held, to calibrate the hold thresholds (D-SEC-5).
CREATE TABLE ticker_refresh_log (
    refresh_id    INTEGER PRIMARY KEY,
    at            TEXT NOT NULL,
    stored_before INTEGER NOT NULL,
    listed        INTEGER NOT NULL,
    added         INTEGER NOT NULL,
    changed       INTEGER NOT NULL,
    dropped       INTEGER NOT NULL,
    conflicts     INTEGER NOT NULL,
    outcome       TEXT NOT NULL CHECK (outcome IN ('applied', 'held', 'forced')),
    review_item   INTEGER REFERENCES review_queue (item_id)
);
