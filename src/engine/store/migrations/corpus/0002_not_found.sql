-- 404 is "no file at this URL" (not_found), not a checked negative (D-SEC-4).
-- SQLite cannot alter a CHECK constraint, so http_cache is rebuilt.

CREATE TABLE http_cache_new (
    cache_key    TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    status       INTEGER NOT NULL,
    content_type TEXT,
    body         BLOB NOT NULL,
    outcome      TEXT NOT NULL CHECK (outcome IN ('ok', 'not_found')),
    fetched_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL
);

INSERT INTO http_cache_new
SELECT cache_key, url, status, content_type, body,
       CASE outcome WHEN 'empty' THEN 'not_found' ELSE outcome END, fetched_at, expires_at
FROM http_cache;

DROP TABLE http_cache;
ALTER TABLE http_cache_new RENAME TO http_cache;
