-- Section splitter (M00_SEARCH Tier 2, D-SRCH-4): titles and splitter version on
-- sections; one split_log row per document so misses can be counted per form.

ALTER TABLE section ADD COLUMN title TEXT;
ALTER TABLE section ADD COLUMN splitter_version TEXT;

CREATE TABLE split_log (
    doc_id           INTEGER PRIMARY KEY REFERENCES document (doc_id) ON DELETE CASCADE,
    form             TEXT,
    splitter_version TEXT NOT NULL,
    outcome          TEXT NOT NULL CHECK (outcome IN ('split', 'fallback', 'single')),
    found            TEXT NOT NULL,   -- JSON list of section labels
    missing          TEXT NOT NULL,   -- JSON list of required items not found
    at               TEXT NOT NULL
);
CREATE INDEX split_log_form ON split_log (form, outcome);
