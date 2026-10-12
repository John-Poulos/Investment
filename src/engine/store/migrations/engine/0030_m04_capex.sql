-- M04 Part 1b capex, trends, guidance record (D-M04-3, -6, -10, -11, -78, -79;
-- M04_BUILD_LOG.md "Migrations"). Both tables are recomputed by the local pass of every
-- refresh (0 SEC requests): a company's rows are replaced as a whole.

-- (1) Capex split per company and fiscal year (D-M04-6). `total` is the own-history
-- series of D-M04-3 (longest consistent tag, D-M04-78); maintenance follows the ladder
-- disclosed → project-level → depreciation (default, capped at total) → D&A (last rung)
-- → not split, one rung per company for the displayed window. Greenwald is a cross-check
-- only (net and gross PP&E), NULL when out of 0…total or not computable. Missing stays
-- NULL with its reason in `note`, never zero (D-M04-9).
CREATE TABLE capex_split (
    cik              TEXT NOT NULL CHECK (length(cik) = 10),
    period_end       TEXT NOT NULL,       -- fiscal year end
    fiscal_label     TEXT NOT NULL,       -- FY2023
    total            NUMERIC,             -- own-history total capex (USD)
    total_tag        TEXT,                -- tag(s) and marks behind `total`
    total_accession  TEXT,
    total_filed      TEXT,
    definition_changed INTEGER NOT NULL DEFAULT 0 CHECK (definition_changed IN (0, 1)),
    maintenance      NUMERIC,
    growth           NUMERIC,
    method           TEXT NOT NULL,       -- depreciation, capped at total capex | … | not split
    rung             TEXT NOT NULL CHECK (rung IN ('disclosed', 'project', 'depreciation',
                                                   'da', 'not_split')),
    rung_value       NUMERIC,             -- the uncapped depreciation or D&A
    greenwald_net    NUMERIC,             -- maintenance by Greenwald on net PP&E, in range only
    greenwald_gross  NUMERIC,
    greenwald_note   TEXT,                -- why missing or out of range
    marks            TEXT,                -- "useful-life change?", "broader tag: …"
    computed_at      TEXT NOT NULL,
    PRIMARY KEY (cik, period_end)
);

-- (2) Guidance outcomes, one per company, metric, basis and period (D-M04-10, -79), plus
-- one row per removal check (kind 'removal', S1.7). Shared scorer `guidance/record.py`;
-- M11 owns R19 weighting and may extend the outcomes ('revised' is reserved for it).
CREATE TABLE guidance_outcome (
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    kind           TEXT NOT NULL CHECK (kind IN ('score', 'removal')),
    metric         TEXT NOT NULL,
    basis          TEXT NOT NULL,
    period         TEXT NOT NULL,          -- fiscal label of the guided (or expected) period
    guidance_id    INTEGER,                -- the guide scored (or, for a removal, last year's)
    guide_text     TEXT,                   -- "$63.0B–$64.0B", "≥ $25.0B", "↑ no figure"
    stated_on      TEXT,
    origin         TEXT,                   -- release | call | ir | owner
    grade          TEXT CHECK (grade IS NULL OR grade IN ('A', 'B', 'C')),
    actual         NUMERIC,
    actual_ref     TEXT,                   -- accession and tag of the actual
    outcome        TEXT NOT NULL CHECK (outcome IN ('hit', 'miss', 'unscored', 'revised',
                                                    'removed', 'expired', 'missing',
                                                    'pending')),
    state          TEXT,                   -- freshness state or why unscored / missing
    revisions_down INTEGER NOT NULL DEFAULT 0,
    revisions_up   INTEGER NOT NULL DEFAULT 0,
    note           TEXT,
    reason_accession TEXT,                 -- stated reason for a dropped guide
    reason_filename  TEXT,
    reason_quote     TEXT,
    computed_at    TEXT NOT NULL,
    PRIMARY KEY (cik, kind, metric, basis, period)
);
CREATE INDEX guidance_outcome_cik ON guidance_outcome (cik, period);
