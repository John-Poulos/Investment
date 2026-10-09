-- M02 plumbing (D-M02-10, D-M02-11): watch tiers and proposal bookkeeping.
-- Personal tables carry an owner id (U3).

-- Tracked = filing index + XBRL facts; promoted = full watchlist jobs. The owner's
-- config/watchlist.toml stays the core list; this table never holds core names.
CREATE TABLE tier_member (
    cik              TEXT PRIMARY KEY CHECK (length(cik) = 10),
    ticker           TEXT NOT NULL,
    tier             TEXT NOT NULL CHECK (tier IN ('tracked', 'promoted')),
    status           TEXT NOT NULL CHECK (status IN ('active', 'removed')),
    theme_key        TEXT,
    reason           TEXT,
    added_at         TEXT NOT NULL,
    added_by         TEXT NOT NULL,
    changed_at       TEXT NOT NULL,
    changed_by       TEXT NOT NULL,
    last_evidence_at TEXT NOT NULL,   -- new theme evidence restarts the 12-month clock
    owner_id         TEXT NOT NULL DEFAULT 'owner'
);

-- One row per proposal key (kind:key): suppresses repeats, holds the weekly overflow
-- and remembers what was shown last, so a rejection returns only on material change.
CREATE TABLE m02_proposal (
    prop_key      TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    cik           TEXT,
    reason        TEXT NOT NULL,
    payload       TEXT,              -- JSON, including the components shown
    status        TEXT NOT NULL CHECK (status IN ('queued', 'overflow')),
    item_id       INTEGER REFERENCES review_queue (item_id),
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    owner_id      TEXT NOT NULL DEFAULT 'owner'
);
CREATE INDEX m02_proposal_status ON m02_proposal (status, first_seen_at);
