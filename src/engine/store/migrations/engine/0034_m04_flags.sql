-- M04 Part 3 restatements, filing events, ratings (D-M04-15, -16, -21, -37, -71, -77;
-- M04_BUILD_LOG.md "Migrations"). Old filings and prior 10-Ks use the existing corpus
-- document and passage tables (no corpus migration).

-- (1) Restatement walk (D-M04-16): one row per change between consecutive filed versions
-- of a value (concept, fiscal year or reported quarter), on periodic forms. Labels are
-- applied in the D-M04-16 order; `residual` is what is left after the labels with an
-- amount. `outcome`: explained (residual within tolerance), review (above both 0.5% and
-- $0.1M), watch (`cf_shift_up` within tolerance). `baseline` = found by the first walk of
-- the company (D-M04-71: recorded and shown, queued only when filed in the last 12 months).
CREATE TABLE restate_step (
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    concept        TEXT NOT NULL,          -- revenue, net_income, operating_cash_flow, ...
    period_start   TEXT NOT NULL,
    period_end     TEXT NOT NULL,
    period_type    TEXT NOT NULL CHECK (period_type IN ('FY', 'Q')),
    from_value     NUMERIC NOT NULL,
    from_tag       TEXT NOT NULL,
    from_accession TEXT NOT NULL,
    from_filed     TEXT NOT NULL,
    to_value       NUMERIC NOT NULL,
    to_tag         TEXT NOT NULL,
    to_accession   TEXT NOT NULL,          -- the filing that changed the value
    to_form        TEXT,
    to_filed       TEXT NOT NULL,
    first_value    NUMERIC NOT NULL,       -- first filed version of the period
    latest_value   NUMERIC NOT NULL,       -- latest filed version of the period
    delta          NUMERIC NOT NULL,       -- to − from
    labels         TEXT NOT NULL,          -- JSON list: family, amount, quoted, passage, quote
    residual       NUMERIC NOT NULL,
    residual_pct   NUMERIC,                -- |residual| ÷ |from_value| (NULL: from = 0)
    outcome        TEXT NOT NULL CHECK (outcome IN ('explained', 'review', 'watch')),
    text_state     TEXT NOT NULL,          -- text read | text not stored | ...
    baseline       INTEGER NOT NULL DEFAULT 0 CHECK (baseline IN (0, 1)),
    owner_outcome  TEXT,                   -- the owner's answer on the m04_restate item
    owner_at       TEXT,
    item_id        INTEGER REFERENCES review_queue (item_id),
    first_seen_at  TEXT NOT NULL,
    computed_at    TEXT NOT NULL,
    PRIMARY KEY (cik, concept, period_start, period_end, to_accession)
);
CREATE INDEX restate_step_cik ON restate_step (cik, to_filed);

-- (2) M04 filing events (D-M04-37, -15, -77; S1.11): 8-K items 1.02, 1.03, 2.04, 2.06,
-- 3.01, 4.01, 4.02 and NT 10-K/10-Q/20-F filings, classified once from the stored `event`
-- and `filing` tables (and the 8-K text where the class needs it). `state` is the current
-- state (fail / warn / info / cleared / resolved); `base_state` the class's own. The owner's
-- resolution is kept across recomputation.
CREATE TABLE m04_event (
    accession      TEXT NOT NULL,
    item           TEXT NOT NULL,          -- 1.03, 3.01, ...; NT 10-Q for late filings
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    form           TEXT NOT NULL,
    filed          TEXT NOT NULL,
    class          TEXT NOT NULL,          -- bankruptcy, delisting, transfer, ...
    base_state     TEXT NOT NULL CHECK (base_state IN ('fail', 'warn', 'info')),
    state          TEXT NOT NULL CHECK (state IN ('fail', 'warn', 'info', 'cleared',
                                                  'resolved')),
    review         INTEGER NOT NULL CHECK (review IN (0, 1)),
    clears_when    TEXT NOT NULL,
    cleared_at     TEXT,
    cleared_by     TEXT,                   -- accession or "owner"
    quote          TEXT,                   -- the sentence that decided the class
    doc_ref        TEXT,                   -- accession/filename of the text read
    note           TEXT NOT NULL,
    owner_resolution TEXT,
    resolved_at    TEXT,
    item_id        INTEGER REFERENCES review_queue (item_id),
    first_seen_at  TEXT NOT NULL,
    computed_at    TEXT NOT NULL,
    PRIMARY KEY (accession, item)
);
CREATE INDEX m04_event_cik ON m04_event (cik, filed);

-- (3) Credit-rating sentences in stored 8-Ks and releases (S3.7, DS17): text only, no
-- agency name needed; one row per sentence.
CREATE TABLE rating_action (
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    accession      TEXT NOT NULL,
    filed          TEXT,
    doc_id         INTEGER NOT NULL,       -- corpus document
    passage_id     INTEGER,
    start_offset   INTEGER NOT NULL,       -- sentence offsets in the document text
    end_offset     INTEGER NOT NULL,
    action         TEXT NOT NULL CHECK (action IN ('downgrade', 'negative_outlook',
                       'watch_negative', 'upgrade', 'positive_outlook', 'affirmed',
                       'mention')),
    from_rating    TEXT,
    to_rating      TEXT,
    agency         TEXT,                   -- only when the sentence names one
    quote          TEXT NOT NULL,
    review         INTEGER NOT NULL CHECK (review IN (0, 1)),
    item_id        INTEGER REFERENCES review_queue (item_id),
    first_seen_at  TEXT NOT NULL,
    PRIMARY KEY (doc_id, start_offset)
);
CREATE INDEX rating_action_cik ON rating_action (cik, filed);
