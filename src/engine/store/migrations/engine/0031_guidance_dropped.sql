-- M04 Part 1b live check 1 (D-M04-85): a removal outside the core families (revenue,
-- gross margin, EPS, operating income, net income, capex, FCF) is stored as 'dropped'
-- ("dropped (information)") and never feeds `guidance_removed`. SQLite cannot alter a
-- CHECK constraint, so the derived table is rebuilt empty: the local pass of every
-- refresh (and `run_financials.py capex --no-sec`) recomputes all rows at 0 requests.
DROP INDEX IF EXISTS guidance_outcome_cik;
DROP TABLE guidance_outcome;
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
                                                    'removed', 'expired', 'dropped',
                                                    'missing', 'pending')),
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
