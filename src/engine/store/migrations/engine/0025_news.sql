-- M02 part 7a: news (D-M02-13, -15, -58). Headline, link, date and a short snippet only
-- (copyright, D-M02-2); every polled item is stored so matching can be re-run.

-- One row per distinct event: the same release via IR RSS, Finnhub and an 8-K is one item
-- with three sources (D-M02-15). Dedupe: normalised URL, else title + date (± 1 day),
-- else a near-identical title of the same company within ± 2 days.
CREATE TABLE news_item (
    item_id       INTEGER PRIMARY KEY,
    url_key       TEXT UNIQUE,          -- normalised URL; NULL for redirect links
    title         TEXT NOT NULL,
    title_key     TEXT NOT NULL,        -- lowercase words, for title + date dedupe
    url           TEXT,
    published_at  TEXT,                 -- as the source states it (UTC); NULL = not given
    snippet       TEXT,                 -- ≤ 300 characters
    grade         TEXT NOT NULL CHECK (grade IN ('A', 'B', 'C')),  -- best of its sources
    first_seen_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX news_item_title ON news_item (title_key);
CREATE INDEX news_item_seen ON news_item (first_seen_at);

CREATE TABLE news_source (
    item_id INTEGER NOT NULL REFERENCES news_item (item_id) ON DELETE CASCADE,
    channel TEXT NOT NULL CHECK (channel IN ('ir_rss', 'finnhub', 'massive', 'trade', 'sec_8k')),
    feed    TEXT NOT NULL,              -- ticker (IR, Finnhub, Massive), outlet key, accession
    origin  TEXT,                       -- source domain or vendor source name the grade used
    grade   TEXT NOT NULL CHECK (grade IN ('A', 'B', 'C')),
    url     TEXT,
    title   TEXT,                       -- as this source gave it
    seen_at TEXT NOT NULL,
    PRIMARY KEY (item_id, channel, feed)
);

-- Companies an item is about: the feed's company, the vendor's ticker, or an alias from
-- config/aliases.toml found in the headline or snippet. Rebuilt by re-matching.
CREATE TABLE news_company (
    item_id INTEGER NOT NULL REFERENCES news_item (item_id) ON DELETE CASCADE,
    cik     TEXT NOT NULL CHECK (length(cik) = 10),
    how     TEXT NOT NULL CHECK (how IN ('feed', 'ticker', 'alias')),
    PRIMARY KEY (item_id, cik)
);
CREATE INDEX news_company_cik ON news_company (cik);

-- Active theme phrases found in the headline or snippet. Rebuilt by re-matching.
CREATE TABLE news_theme (
    item_id  INTEGER NOT NULL REFERENCES news_item (item_id) ON DELETE CASCADE,
    theme_id INTEGER NOT NULL REFERENCES theme (theme_id),
    phrase   TEXT NOT NULL,
    PRIMARY KEY (item_id, theme_id)
);
CREATE INDEX news_theme_theme ON news_theme (theme_id);

-- Per feed: conditional-GET validators and the last outcome (shown in the run report).
CREATE TABLE news_feed_state (
    feed          TEXT PRIMARY KEY,     -- channel:key
    etag          TEXT,
    last_modified TEXT,
    last_ok_at    TEXT,
    last_status   INTEGER,
    last_error    TEXT,
    items_last    INTEGER,
    checked_at    TEXT NOT NULL
);

-- First mention of a theme by a watchlist/tracked company in its own stored documents
-- (D-M02-58 (3)). A row is written the first time a (company, theme) pair is scanned:
-- baseline = 1 for what was already there; a later first mention is an event (baseline 0).
CREATE TABLE theme_first_mention (
    cik        TEXT NOT NULL CHECK (length(cik) = 10),
    theme_id   INTEGER NOT NULL REFERENCES theme (theme_id),
    baseline   INTEGER NOT NULL CHECK (baseline IN (0, 1)),
    phrase     TEXT,                    -- NULL while no mention is stored
    source     TEXT CHECK (source IN ('document', 'ir_rss')),
    accession  TEXT,                    -- document mentions
    filename   TEXT,
    section    TEXT,
    item_id    INTEGER REFERENCES news_item (item_id),  -- IR headline mentions
    dated      TEXT,                    -- filing date or headline date
    quote      TEXT,
    scanned_at TEXT NOT NULL,
    found_at   TEXT,
    PRIMARY KEY (cik, theme_id)
);
