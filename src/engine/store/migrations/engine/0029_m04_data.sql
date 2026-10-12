-- M04 Part 1a data foundation (D-M04-2, -9, -36, -61, -74; M04_BUILD_LOG.md "Migrations").

-- (1) D13 signal record rebuilt (D-M04-9, D-M04-74): keyed by CIK, ticker kept for display.
-- Numbers go in `value`, states and enums in `value_text` (text in a NUMERIC column sorts
-- above every number). A missing signal has both empty and method "missing: <reason>";
-- only such rows may lack a grade or a source.
CREATE TABLE signal_new (
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    ticker         TEXT,
    module_id      TEXT NOT NULL,
    signal         TEXT NOT NULL,
    timeframe      TEXT NOT NULL CHECK (timeframe IN ('MY', 'PT', 'ST')),
    as_of          TEXT NOT NULL,
    value          NUMERIC CHECK (value IS NULL OR typeof(value) IN ('integer', 'real')),
    value_text     TEXT,
    evidence_grade TEXT CHECK (evidence_grade IS NULL OR evidence_grade IN ('A', 'B', 'C')),
    source_ref     TEXT,
    method         TEXT NOT NULL,
    PRIMARY KEY (cik, module_id, signal, timeframe, as_of),
    CHECK (value IS NOT NULL OR value_text IS NOT NULL OR method LIKE 'missing:%'),
    CHECK ((evidence_grade IS NOT NULL AND source_ref IS NOT NULL)
           OR (value IS NULL AND value_text IS NULL AND method LIKE 'missing:%'))
);

-- Existing rows (none written before Part 1a): CIK from the ticker span that covers
-- as_of, else the latest span; text found in `value` moves to `value_text`.
INSERT INTO signal_new (cik, ticker, module_id, signal, timeframe, as_of, value, value_text,
                        evidence_grade, source_ref, method)
SELECT coalesce(
           (SELECT t.cik FROM ticker t WHERE t.ticker = s.ticker AND t.valid_from <= s.as_of
              AND (t.valid_to IS NULL OR t.valid_to > s.as_of) ORDER BY t.valid_from DESC LIMIT 1),
           (SELECT t.cik FROM ticker t WHERE t.ticker = s.ticker ORDER BY t.valid_from DESC LIMIT 1),
           '0000000000'),
       s.ticker, s.module_id, s.signal, s.timeframe, s.as_of,
       CASE WHEN typeof(s.value) IN ('integer', 'real') THEN s.value END,
       CASE WHEN typeof(s.value) = 'text' THEN s.value END,
       s.evidence_grade, s.source_ref,
       CASE WHEN (SELECT count(*) FROM ticker t WHERE t.ticker = s.ticker) = 0
            THEN 'cik unresolved at migration 0029; ' || s.method ELSE s.method END
FROM signal s;

DROP TABLE signal;
ALTER TABLE signal_new RENAME TO signal;
CREATE INDEX signal_ticker ON signal (ticker);

-- (2) Predecessor and shell CIKs (S1.1 case 20; M04_BUILD_LOG Part 1a).
-- kind 'predecessor': another CIK filed for the company until boundary_date (facts filed on
-- or before it are read for the successor). kind 'spac_shell': same CIK, periods ending
-- before boundary_date belong to the shell (keyed on period end, D-M04-8).
CREATE TABLE entity_link (
    predecessor_cik TEXT NOT NULL CHECK (length(predecessor_cik) = 10),
    successor_cik   TEXT NOT NULL CHECK (length(successor_cik) = 10),
    boundary_date   TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('predecessor', 'spac_shell')),
    name            TEXT,
    source          TEXT NOT NULL,
    PRIMARY KEY (predecessor_cik, successor_cik, kind)
);
INSERT INTO entity_link VALUES
    ('0001288776', '0001652044', '2016-02-11', 'predecessor', 'Google Inc.',
     'M04_BUILD_LOG Part 1a (Alphabet holding-company reorganization)'),
    ('0001058057', '0001835632', '2021-03-16', 'predecessor', 'Marvell Technology Group Ltd.',
     'M04_BUILD_LOG Part 1a (domestication to Marvell Technology, Inc.)'),
    ('0002007825', '0002007825', '2026-02-13', 'spac_shell', 'Churchill Capital Corp X',
     'Q2 2026 10-Q; 8-K 2.01 + 5.06 filed 2026-02-17 (closing 2026-02-13)');

-- (3) Cover share counts read from a filing's R1 page, one row per class (D-M04-2).
-- class_label '' = one count without a class. Raw counts as filed; splits are applied
-- at read time (split guard). The flag is the cover's DocumentFinStmtErrorCorrectionFlag.
CREATE TABLE cover_shares (
    accession             TEXT NOT NULL,
    cik                   TEXT NOT NULL CHECK (length(cik) = 10),
    class_label           TEXT NOT NULL,
    shares                NUMERIC NOT NULL,
    cover_date            TEXT NOT NULL,
    error_correction_flag INTEGER CHECK (error_correction_flag IN (0, 1)),
    form                  TEXT,
    filed                 TEXT,
    source_url            TEXT NOT NULL,
    read_at               TEXT NOT NULL,
    PRIMARY KEY (accession, class_label)
);
CREATE INDEX cover_shares_cik ON cover_shares (cik, cover_date);

-- (4) Filing status per company and period (S1.6, D-M04-36, D-M04-61), re-evaluated on
-- every logon run from the calendar.
CREATE TABLE filing_status (
    cik             TEXT NOT NULL CHECK (length(cik) = 10),
    period_end      TEXT NOT NULL,
    form            TEXT NOT NULL,
    category        TEXT,               -- carried filer category; NULL = unknown
    category_source TEXT NOT NULL,      -- submissions | Rule 12b-2 from float | missing
    deadline_days   INTEGER,
    due_date        TEXT NOT NULL,
    nt_accession    TEXT,
    filed           TEXT,
    accession       TEXT,
    status          TEXT NOT NULL CHECK (status IN ('current', 'stale', 'overdue')),
    note            TEXT,
    evaluated_at    TEXT NOT NULL,
    PRIMARY KEY (cik, period_end, form)
);

-- (5) Filer category from submissions (`category`, e.g. "Large accelerated filer").
ALTER TABLE entity ADD COLUMN category TEXT;
