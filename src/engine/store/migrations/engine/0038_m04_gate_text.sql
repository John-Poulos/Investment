-- M04 Part 4b-lite survival gate: going-concern and covenant text (D-M04-34, -71, -95…98;
-- D-STO-28; M04_BUILD_LOG.md "Migrations").
-- One row per classified sentence of stored periodic text (10-K, 10-Q, 20-F, 40-F, their
-- amendments, 6-K and their EX-10 / EX-99 exhibits). The quote is cut from the stored
-- document by its offsets and re-verified on every pass (D21): a document whose text
-- changed is scanned again. Which rows act on the gate is decided at read time (the
-- company's current report as of the gate's date, D-M04-96), so the table holds history
-- as well. The per-document scan record and the first-scan marker live in `refresh_state`
-- (`m04_gate_text:<cik>`). Rows without an owner answer or a review item are replaced when
-- the classifier changes; answered or reviewed rows are kept.
CREATE TABLE gate_text (
    accession     TEXT NOT NULL,
    filename      TEXT NOT NULL,
    start_offset  INTEGER NOT NULL,       -- sentence span in document.text
    end_offset    INTEGER NOT NULL CHECK (end_offset > start_offset),
    cik           TEXT NOT NULL CHECK (length(cik) = 10),
    form          TEXT NOT NULL,          -- the filing's form (10-K, 10-Q, 6-K, ...)
    doc_type      TEXT,                   -- the document's type (10-K, EX-10.1, EX-99.1)
    filed         TEXT NOT NULL,
    period_end    TEXT,                   -- the report's period; keys the spac_shell exclusion
    family        TEXT NOT NULL CHECK (family IN ('going_concern', 'covenant')),
    class         TEXT NOT NULL,          -- auditor_gc, management_exists, alleviated, ...
    effect        TEXT NOT NULL CHECK (effect IN ('fail', 'warn', 'hypothetical', 'none',
                                                  'excluded')),
    quote         TEXT NOT NULL,          -- the deciding sentence, whitespace-normalised
    passage_id    INTEGER,                -- corpus passage holding the sentence
    doc_id        INTEGER,                -- corpus document
    exhibit       INTEGER NOT NULL CHECK (exhibit IN (0, 1)),
    note          TEXT NOT NULL DEFAULT '',  -- why (exclusion reason, alleviation nearby, ...)
    baseline      INTEGER NOT NULL CHECK (baseline IN (0, 1)),  -- found by the first scan
    item_id       INTEGER REFERENCES review_queue (item_id),
    owner_outcome TEXT CHECK (owner_outcome IN ('noted', 'treat_as_fail', 'misread')),
    owner_at      TEXT,
    first_seen_at TEXT NOT NULL,
    computed_at   TEXT NOT NULL,
    PRIMARY KEY (accession, filename, start_offset)
);
CREATE INDEX gate_text_cik ON gate_text (cik, filed);
