-- Passages (M00_SEARCH Tier 2, D-SRCH-7): paragraph-aligned chunks of each section,
-- offsets into document.text. Passages are the unit that is ranked and cited.
-- passage_fts is self-contained (snippet()/highlight() work); passage_id = its rowid.

CREATE TABLE passage (
    passage_id      INTEGER PRIMARY KEY,
    section_id      INTEGER NOT NULL REFERENCES section (section_id) ON DELETE CASCADE,
    doc_id          INTEGER NOT NULL REFERENCES document (doc_id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,     -- order within the section
    start_offset    INTEGER NOT NULL,
    end_offset      INTEGER NOT NULL CHECK (end_offset > start_offset),
    chunker_version TEXT NOT NULL,
    UNIQUE (section_id, seq)
);
CREATE INDEX passage_doc ON passage (doc_id);

CREATE VIRTUAL TABLE passage_fts USING fts5 (
    label,
    body,
    tokenize = 'porter unicode61'
);
