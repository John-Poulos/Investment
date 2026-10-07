-- Form 4 documents and richer transaction rows (D-SEC-10, R7, R13, R22).

CREATE TABLE form4_doc (
    accession        TEXT PRIMARY KEY,
    issuer_cik       TEXT NOT NULL CHECK (length(issuer_cik) = 10),
    issuer_name      TEXT,
    issuer_ticker    TEXT,
    doc_type         TEXT NOT NULL,     -- 4 or 4/A
    period_of_report TEXT,
    filed            TEXT,
    filename         TEXT NOT NULL,
    aff_10b5_1       INTEGER,           -- 2023+ checkbox; NULL = field absent
    owners           TEXT NOT NULL,     -- JSON list of reporting owners with roles
    transactions     INTEGER NOT NULL,
    parser_version   TEXT NOT NULL,
    parsed_at        TEXT NOT NULL
);
CREATE INDEX form4_issuer ON form4_doc (issuer_cik, period_of_report);

ALTER TABLE insider_txn ADD COLUMN officer_title TEXT;
ALTER TABLE insider_txn ADD COLUMN deemed_date TEXT;
ALTER TABLE insider_txn ADD COLUMN equity_swap INTEGER;
ALTER TABLE insider_txn ADD COLUMN nature_of_ownership TEXT;
ALTER TABLE insider_txn ADD COLUMN conversion_price NUMERIC;
ALTER TABLE insider_txn ADD COLUMN underlying_title TEXT;
ALTER TABLE insider_txn ADD COLUMN underlying_shares NUMERIC;
ALTER TABLE insider_txn ADD COLUMN footnotes TEXT;   -- JSON {id: text} referenced by the row
-- Evidence behind is_10b5_1: row footnote (yes/no), form checkbox unset (no),
-- form checkbox set but row not identified (NULL), NULL = not disclosed.
ALTER TABLE insider_txn ADD COLUMN plan_basis TEXT;
