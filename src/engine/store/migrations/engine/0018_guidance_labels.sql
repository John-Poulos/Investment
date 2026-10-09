-- Guidance accuracy loop (M02 part 4b, D-M02-24). Labels say whether the parser was right
-- about a sentence: from the owner's "wrong" button, the weekly random audit, plausibility
-- flags or an owner-triggered Gemini cross-check. Labels are keyed by document and quote
-- offsets (not guidance_id, which changes on every re-scan), so they survive re-scans: a
-- row labelled wrong is not inserted again. They are local data (call text is vendor
-- text and stays off GitHub); each new parser version is re-checked against all of them.

CREATE TABLE guidance_label (
    label_id       INTEGER PRIMARY KEY,
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    accession      TEXT NOT NULL,
    filename       TEXT NOT NULL,
    quote_start    INTEGER NOT NULL,
    quote_end      INTEGER NOT NULL,
    quote          TEXT NOT NULL,
    metric         TEXT,               -- what the parser stored (NULL for a missed sentence)
    period         TEXT,
    value_text     TEXT,
    verdict        TEXT NOT NULL CHECK (verdict IN ('right', 'wrong', 'missed')),
    reason         TEXT CHECK (reason IN ('wrong_company', 'segment', 'past_actual',
                                          'wrong_period', 'wrong_value', 'not_guidance',
                                          'missed_guidance', 'other')),
    note           TEXT,
    found_by       TEXT NOT NULL CHECK (found_by IN ('owner', 'audit', 'plausibility',
                                                     'gemini')),
    origin         TEXT NOT NULL,      -- release | call | ir
    parser_version TEXT NOT NULL,      -- the version that produced (or skipped) the sentence
    labelled_by    TEXT NOT NULL,
    labelled_at    TEXT NOT NULL,
    item_id        INTEGER,            -- the review item answered, if any (undo reopens it)
    correction_id  INTEGER             -- owner-entered guidance row stored with the label
);
CREATE INDEX guidance_label_doc ON guidance_label (accession, filename);

-- Call sentences the parser looked at and set aside, with why (sampled by the audit).
CREATE TABLE guidance_skip (
    accession      TEXT NOT NULL,
    filename       TEXT NOT NULL,
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    start_offset   INTEGER NOT NULL,
    end_offset     INTEGER NOT NULL,
    reason         TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    PRIMARY KEY (accession, filename, start_offset)
);
