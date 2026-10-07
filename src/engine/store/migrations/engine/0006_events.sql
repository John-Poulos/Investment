-- Typed 8-K events, one row per item per filing (D-SEC-11).

CREATE TABLE event (
    accession   TEXT NOT NULL,
    item        TEXT NOT NULL,          -- e.g. 2.02, 4.02; 6-K for foreign current reports
    cik         TEXT NOT NULL CHECK (length(cik) = 10),
    form        TEXT NOT NULL,          -- 8-K, 8-K/A, 6-K, 6-K/A
    filed       TEXT NOT NULL,
    accepted_at TEXT,
    report_date TEXT,
    category    TEXT NOT NULL,          -- earnings, red_flag, agreement, people, capital, ...
    severity    TEXT NOT NULL CHECK (severity IN ('high', 'medium', 'low', 'none')),
    title       TEXT NOT NULL,
    modules     TEXT NOT NULL,          -- JSON list of module ids that consume the event
    amended     INTEGER NOT NULL CHECK (amended IN (0, 1)),
    catalog     TEXT NOT NULL,          -- catalog version that classified it
    PRIMARY KEY (accession, item, cik)
);
CREATE INDEX event_cik_filed ON event (cik, filed);
CREATE INDEX event_category ON event (category, severity, filed);
