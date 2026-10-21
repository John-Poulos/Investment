-- M05 Part 2: committed future spend (docs/M05_FUTURE_SPEND.md rules 6–7; D-M05-2, -3,
-- D-M05-18…; D-SEC-31; D-STO-32).
-- One row per commitment amount: an XBRL value of one purchase-obligation tag (per tag,
-- never merged), or an amount in a sentence of a stored 10-K / 10-Q main document, its
-- quote cut from the stored text by offsets and verified mechanically (D21). Customer
-- deposit wording is kept here too (category customer_deposit; never a commitment, never
-- added to RPO, D-M05-6). Derived data: the M05 pass replaces a company's rows on every run
-- (first_seen_at carried by `key`); `commitment_cover` is a D13 row in `signal`.
CREATE TABLE future_commitment (
    commitment_id  INTEGER PRIMARY KEY,
    key            TEXT NOT NULL UNIQUE,  -- text:<accession>/<filename>@<amount start> | xbrl:<tag>@<as_of>
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    as_of          TEXT NOT NULL,         -- the report's period end (XBRL: the instant)
    stated_date    TEXT,                  -- after-period lines: the date the sentence states
    category       TEXT NOT NULL CHECK (category IN ('supply_capacity', 'ppe', 'cloud',
                       'investment', 'other', 'purchase_total', 'lease_not_commenced',
                       'customer_deposit', 'as_tagged')),
    amount         REAL NOT NULL,         -- dollars, as stated
    source         TEXT NOT NULL CHECK (source IN ('xbrl', 'text')),
    tag            TEXT,                  -- xbrl rows: us-gaap:PurchaseObligation, ...
    quote          TEXT,                  -- text rows: the sentence, whitespace-normalised
    accession      TEXT NOT NULL,
    filename       TEXT,                  -- text rows: the corpus document
    form           TEXT,
    filed          TEXT NOT NULL,
    start_offset   INTEGER,               -- sentence span in document.text
    end_offset     INTEGER,
    amount_start   INTEGER,               -- the amount's span in document.text
    amount_end     INTEGER,
    passage_id     INTEGER,               -- corpus passage holding the sentence
    scope_label    TEXT NOT NULL,         -- what the amount covers, as stated or as tagged
    cancellable    INTEGER NOT NULL CHECK (cancellable IN (0, 1)),
    after_period   INTEGER NOT NULL CHECK (after_period IN (0, 1)),
    grade          TEXT NOT NULL CHECK (grade IN ('A', 'B', 'C')),
    finder_version TEXT NOT NULL,
    first_seen_at  TEXT NOT NULL,
    computed_at    TEXT NOT NULL
);
CREATE INDEX future_commitment_cik ON future_commitment (cik, as_of);
