-- M04 Part 2 peer facts (D-M04-5, -52, -75; M04_BUILD_LOG.md "Migrations").
-- One companyfacts download per confirmed SEC peer, trimmed to M04's tags and stored in
-- `fact` under the peer's CIK; the file itself is not cached (SB.16). This table records
-- the latest fetch per peer and a newer periodic filing seen in the daily index, which the
-- refresh's M04 SEC part re-fetches (D-M04-70). `peer_group` / `peer_member` (0001) are
-- written by the Part 1c setup page when the owner confirms a peer set ("M04 peers <cik>").
CREATE TABLE peer_fetch (
    cik            TEXT PRIMARY KEY CHECK (length(cik) = 10),
    name           TEXT,                   -- companyfacts entityName, else the member name
    fetched_at     TEXT NOT NULL,          -- last attempt
    outcome        TEXT NOT NULL CHECK (outcome IN ('ok', 'not_found', 'failed')),
    ok_at          TEXT,                   -- last successful fetch
    tags_total     INTEGER,                -- tags in the downloaded file
    tags_kept      INTEGER,                -- tags in M04's concept map that the file has
    rows_kept      INTEGER,                -- fact rows in the trimmed file
    rows_new       INTEGER,                -- of which new in `fact`
    mb             NUMERIC,                -- downloaded size, MB
    fiscal_year_end TEXT,                  -- MMDD inferred from the latest annual fact
    latest_end     TEXT,                   -- latest period end among the kept facts
    latest_filed   TEXT,                   -- latest filed date among the kept facts
    due_accession  TEXT,                   -- a newer 10-K/10-Q/20-F/40-F seen in the daily
    due_form       TEXT,                   -- index after ok_at: re-fetch on the next
    due_filed      TEXT,                   -- refresh (cleared by a successful fetch)
    detail         TEXT                    -- failure reason or note
);
CREATE INDEX peer_fetch_due ON peer_fetch (due_filed);
