-- M07 Part 1 insider signals (D-M07-1...5, D-M07-9...; D-SEC-27; D-STO-30).
-- form4_holding: holding lines without a transaction (parser form4-2), so a stake can be
-- summed over every non-derivative line of a form (D-M07-4; Huang: 9 lines). Derivative
-- holdings are stored too and shown apart.
CREATE TABLE form4_holding (
    accession       TEXT NOT NULL,
    line            INTEGER NOT NULL,     -- 1..n within the form's holding lines
    table_kind      TEXT NOT NULL CHECK (table_kind IN ('non_derivative', 'derivative')),
    title           TEXT,                 -- security title
    shares          NUMERIC,              -- shares (or derivative units) owned; NULL = not stated
    direct_indirect TEXT CHECK (direct_indirect IN ('D', 'I')),
    nature          TEXT,                 -- nature of indirect ownership ("By Trust")
    footnotes       TEXT,                 -- JSON {id: text} referenced by the line
    PRIMARY KEY (accession, line)
);

-- insider_class: the Cohen-Malloy-Pomorski class per (owner CIK, issuer CIK, calendar year),
-- from the owner's open-market P/S rows in the 3 prior calendar years (S09; D-M07-1, -2).
-- Derived: replaced per issuer on every M07 pass.
CREATE TABLE insider_class (
    owner_cik   TEXT NOT NULL,
    issuer_cik  TEXT NOT NULL CHECK (length(issuer_cik) = 10),
    year        INTEGER NOT NULL,
    class       TEXT NOT NULL CHECK (class IN ('routine', 'opportunistic', 'unclassified')),
    years_used  TEXT NOT NULL,            -- JSON list of the 3 prior years
    months_seen TEXT NOT NULL,            -- JSON {year: [months with a P/S row]}
    reason      TEXT NOT NULL DEFAULT '', -- why (common month, missing year, history start)
    computed_at TEXT NOT NULL,
    PRIMARY KEY (owner_cik, issuer_cik, year)
);

-- 4/A link (rule 7): a row of an earlier Form 4 replaced by a 4/A row matched on
-- (owner, transaction date, shares) carries the 4/A's accession; set by the M07 pass.
ALTER TABLE insider_txn ADD COLUMN replaced_by TEXT;
