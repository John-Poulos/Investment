-- M02 part 7b: official feeds (D-M02-13, -15, -58, -60). Grade A (government sources).
-- Every row keeps its first-seen date (point-in-time backtests, D-M02-15); missing stays
-- missing (no row), never zero.

-- arXiv: new preprints per theme phrase per calendar month (research momentum, never money
-- flow). One row per (phrase, month) once counted; a failed count leaves no row.
CREATE TABLE arxiv_count (
    phrase     TEXT NOT NULL,           -- lowercase, unquoted theme phrase
    month      TEXT NOT NULL,           -- YYYY-MM (submittedDate, GMT)
    n          INTEGER NOT NULL CHECK (n >= 0),  -- opensearch:totalResults
    query      TEXT NOT NULL,           -- search_query as sent
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (phrase, month)
);

-- USAspending: prime awards found by recipient search for watchlist/tracked companies.
-- Amounts are obligations (not cash paid); DoD data arrive with a 90-day delay.
CREATE TABLE usa_award (
    award_key        TEXT PRIMARY KEY,  -- generated_internal_id
    award_id         TEXT NOT NULL,     -- "Award ID" (PIID / FAIN)
    award_group      TEXT NOT NULL CHECK (award_group IN ('contracts', 'grants')),
    award_type       TEXT,              -- Contract Award Type / Award Type, as stated
    recipient_name   TEXT NOT NULL,     -- as stated
    recipient_uei    TEXT,
    recipient_id     TEXT,              -- USAspending recipient hash (…-C child, -P parent, -R)
    amount           REAL,              -- "Award Amount": total obligated to date; NULL = not given
    base_date        TEXT,              -- Base Obligation Date (award start of obligations)
    start_date       TEXT,
    last_modified    TEXT,
    agency           TEXT,
    sub_agency       TEXT,
    description      TEXT,              -- ≤ 300 characters
    searched_cik     TEXT NOT NULL CHECK (length(searched_cik) = 10),  -- whose search found it
    search_term      TEXT NOT NULL,
    first_seen_at    TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX usa_award_recipient ON usa_award (recipient_id);
CREATE INDEX usa_award_searched ON usa_award (searched_cik);

-- Recipient → company: conservative. 'name' = the stated name equals a known name of the
-- company (SEC name or config/aliases.toml) after case, punctuation, a leading "The" and the
-- legal suffix; 'parent' = the recipient's USAspending parent (name or UEI) maps that way;
-- 'none' = left unmapped and shown as such.
CREATE TABLE usa_recipient (
    recipient_id TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    uei          TEXT,
    level        TEXT,                  -- P / C / R when the profile was read
    parent_name  TEXT,
    parent_uei   TEXT,
    cik          TEXT CHECK (cik IS NULL OR length(cik) = 10),
    how          TEXT NOT NULL CHECK (how IN ('name', 'parent', 'none')),
    profile_at   TEXT,                  -- when the recipient profile was read (NULL = not yet)
    checked_at   TEXT NOT NULL
);
CREATE INDEX usa_recipient_cik ON usa_recipient (cik);

-- Federal Register documents and Congress.gov bills matching active theme phrases.
CREATE TABLE fedreg_doc (
    document_number  TEXT PRIMARY KEY,
    doc_type         TEXT NOT NULL,     -- Rule / Proposed Rule / Notice, as stated
    title            TEXT NOT NULL,
    agencies         TEXT,              -- names joined by "; "
    publication_date TEXT NOT NULL,
    url              TEXT,
    abstract         TEXT,              -- ≤ 300 characters
    first_seen_at    TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE congress_bill (
    bill_id            TEXT PRIMARY KEY,  -- e.g. 119-hr-1234
    congress           INTEGER NOT NULL,
    bill_type          TEXT NOT NULL,
    number             TEXT NOT NULL,
    title              TEXT NOT NULL,
    summary            TEXT,              -- ≤ 300 characters of the latest summary, if read
    latest_action_date TEXT,
    latest_action      TEXT,
    status             TEXT NOT NULL CHECK (status IN ('introduced', 'enacted')),
    url                TEXT,              -- congress.gov page
    update_date        TEXT,
    first_seen_at      TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

-- Which theme phrase found each document or bill (Federal Register: full-text search by
-- phrase; Congress: the phrase in the title or summary).
CREATE TABLE official_theme (
    source   TEXT NOT NULL CHECK (source IN ('fedreg', 'congress')),
    ref      TEXT NOT NULL,               -- document_number or bill_id
    theme_id INTEGER NOT NULL REFERENCES theme (theme_id),
    phrase   TEXT NOT NULL,
    found_at TEXT NOT NULL,
    PRIMARY KEY (source, ref, theme_id)
);
CREATE INDEX official_theme_theme ON official_theme (theme_id);
