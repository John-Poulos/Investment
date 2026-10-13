-- M04 Part 4a survival gate: numbers (D-M04-32, -86; M04_BUILD_LOG.md "Migrations").
-- The gate's states and figures are D13 signals (`survival_gate`, `runway_q`, …); the
-- turn-to-fail bookkeeping lives in `refresh_state` (`m04_gate:<cik>`), so the only new
-- table is the confirmed undrawn credit that feeds the runway.

-- Undrawn committed credit (D-M04-32, S4.2; D-M04-86). Only stated availability counts,
-- never facility size. A line counts in the runway when it is confirmed, matures more than
-- 12 months after the gate's balance-sheet date, and was stated for that balance sheet
-- (`as_of` within 45 days before it): a newer 10-Q or 10-K needs a new confirmation (pack
-- S4.2, "expires at the next 10-Q or 10-K"). Part 4a writes owner entries (origin 'owner',
-- status 'confirmed'); Part 4b's finder proposes lines from verified sentences into the
-- same table (origin 'finder', status 'proposed', `passage_id`, an `m04_credit_line` item)
-- and a confirmation sets status, confirmed_by and confirmed_at. Rows are never deleted:
-- a wrong entry is 'withdrawn' (who and when kept).
CREATE TABLE credit_line (
    line_id      INTEGER PRIMARY KEY,
    cik          TEXT NOT NULL CHECK (length(cik) = 10),
    facility     TEXT NOT NULL,          -- e.g. "five-year revolver", "ABL"
    amount       NUMERIC NOT NULL CHECK (amount > 0),  -- undrawn available, USD
    maturity     TEXT NOT NULL,          -- YYYY-MM-DD
    as_of        TEXT NOT NULL,          -- balance-sheet date the availability is stated for
    source_text  TEXT NOT NULL,          -- the sentence or the owner's source note
    source_url   TEXT,
    accession    TEXT,                   -- when the source is a filing
    passage_id   INTEGER,                -- Part 4b: the verified passage
    origin       TEXT NOT NULL CHECK (origin IN ('owner', 'finder')),
    status       TEXT NOT NULL CHECK (status IN ('proposed', 'confirmed', 'rejected',
                                                 'withdrawn')),
    grade        TEXT NOT NULL CHECK (grade IN ('A', 'B')),  -- A with a filing source (D-M04-9)
    proposed_at  TEXT NOT NULL,
    confirmed_by TEXT,
    confirmed_at TEXT,
    closed_by    TEXT,                   -- who rejected or withdrew it
    closed_at    TEXT,
    item_id      INTEGER REFERENCES review_queue (item_id),
    note         TEXT,
    CHECK (status != 'confirmed' OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL))
);
CREATE INDEX credit_line_cik ON credit_line (cik, status, as_of);
