-- One accession can appear under several CIKs (Form 4: issuer and reporting owner;
-- co-registrants). filing.cik is the CIK whose submissions first listed it;
-- filing_cik records every CIK that lists it (D-SEC-6).

CREATE TABLE filing_cik (
    accession TEXT NOT NULL REFERENCES filing (accession) ON DELETE CASCADE,
    cik       TEXT NOT NULL CHECK (length(cik) = 10),
    PRIMARY KEY (accession, cik)
);
CREATE INDEX filing_cik_by_cik ON filing_cik (cik);

INSERT INTO filing_cik (accession, cik) SELECT accession, cik FROM filing;

ALTER TABLE filing ADD COLUMN is_inline_xbrl INTEGER;
ALTER TABLE filing ADD COLUMN size INTEGER;
