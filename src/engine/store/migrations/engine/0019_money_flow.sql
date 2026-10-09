-- M02 part 3, money flow (D-M02-28…32).

-- Capex actuals the company states in words ("CapEx was $44.9 billion in the second
-- quarter"), from releases (grade A) and calls (B; A when a release states the same
-- figure). Never guidance. Used to reconcile each XBRL recipe and, when the recipe is
-- approximate, partial or off by > 1%, as the actual shown (D-M02-32).
CREATE TABLE capex_stated (
    stated_id      INTEGER PRIMARY KEY,
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    accession      TEXT NOT NULL,
    filename       TEXT NOT NULL,
    origin         TEXT NOT NULL CHECK (origin IN ('release', 'call', 'ir')),
    grade          TEXT NOT NULL CHECK (grade IN ('A', 'B')),
    period         TEXT NOT NULL,      -- company fiscal label: FY2026 Q2 | FY2026
    period_how     TEXT NOT NULL,      -- 'stated' or 'release quarter' (no period word)
    kind           TEXT NOT NULL CHECK (kind IN ('approx', 'point')),
    value          NUMERIC NOT NULL,   -- USD
    clause         TEXT,               -- "including principal payments on finance leases"
    stated_on      TEXT NOT NULL,
    quote          TEXT NOT NULL,
    quote_start    INTEGER NOT NULL,
    quote_end      INTEGER NOT NULL,
    parser_version TEXT NOT NULL,
    UNIQUE (accession, filename, quote_start, period)
);
CREATE INDEX capex_stated_cik ON capex_stated (cik, period);

-- How a cash-flow tag counts in the capital-allocation block (D-M02-31 (5)). Built-in
-- us-gaap mappings live in code; these rows are the owner's decisions on m02_tag items.
-- cik NULL = a standard tag, applies to every company; extension tags carry their cik.
CREATE TABLE fin_tag_map (
    map_id     INTEGER PRIMARY KEY,
    cik        TEXT CHECK (cik IS NULL OR length(cik) = 10),
    taxonomy   TEXT NOT NULL,
    tag        TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('debt_raised', 'debt_repaid', 'equity_issued',
                                             'buybacks', 'dividends', 'other', 'ignore')),
    item_id    INTEGER,
    mapped_by  TEXT NOT NULL,
    mapped_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX fin_tag_map_key ON fin_tag_map (ifnull(cik, ''), taxonomy, tag);

-- Sentences tying a spender's spending to a theme (D-M02-5, D-M02-30 (3)): code finds,
-- owner confirms through an m02_spender review item.
CREATE TABLE spender_link (
    link_id      INTEGER PRIMARY KEY,
    cik          TEXT NOT NULL CHECK (length(cik) = 10),
    theme_id     INTEGER NOT NULL REFERENCES theme (theme_id),
    accession    TEXT NOT NULL,
    filename     TEXT NOT NULL,
    origin       TEXT NOT NULL CHECK (origin IN ('filing', 'release', 'call', 'ir')),
    grade        TEXT NOT NULL CHECK (grade IN ('A', 'B')),
    phrase       TEXT NOT NULL,      -- the theme phrase found
    quote        TEXT NOT NULL,
    quote_start  INTEGER NOT NULL,
    quote_end    INTEGER NOT NULL,
    filed        TEXT,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'confirmed',
                                                              'rejected')),
    item_id      INTEGER,
    found_at     TEXT NOT NULL,
    decided_at   TEXT,
    UNIQUE (cik, theme_id, accession, filename, quote_start)
);
CREATE INDEX spender_link_theme ON spender_link (theme_id, status);
