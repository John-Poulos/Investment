-- M02 part 5b, financing and equity links (D-M02-41…45).
-- Direction everywhere: the financer's money or equity goes to the other company
-- (a_to_b = A finances / invests in / grants equity to / backstops B).

-- 13F-HR filings read (D-M02-45 (1)). Values in dollars (×1000 before 2023-01-01).
CREATE TABLE fin_13f (
    accession    TEXT PRIMARY KEY,
    filer_cik    TEXT NOT NULL CHECK (length(filer_cik) = 10),
    form         TEXT NOT NULL,
    period       TEXT NOT NULL,           -- report quarter end, YYYY-MM-DD
    filed        TEXT NOT NULL,
    amend_type   TEXT,                    -- NULL (original) | RESTATEMENT | NEW HOLDINGS
    scale        INTEGER NOT NULL,        -- 1000 (thousands, filed before 2023-01-03) or 1
    entries      INTEGER,                 -- tableEntryTotal as reported
    value_total  NUMERIC,                 -- tableValueTotal in dollars
    row_sum      NUMERIC,                 -- sum of information-table values in dollars
    status       TEXT NOT NULL CHECK (status IN ('read', 'failed', 'no_table')),
    detail       TEXT,
    read_at      TEXT NOT NULL
);
CREATE INDEX fin_13f_filer ON fin_13f (filer_cik, period);

-- Structured holdings: 13F rows (summed by CUSIP, title and put/call) and 13D/13G
-- schedules. Stored automatically, grade A, only when the issuer resolves to exactly one
-- known company and the checks pass; otherwise held for review (D-M02-42).
CREATE TABLE fin_holding (
    holding_id    INTEGER PRIMARY KEY,
    source        TEXT NOT NULL CHECK (source IN ('13F', '13D', '13G')),
    accession     TEXT NOT NULL,
    filer_cik     TEXT NOT NULL CHECK (length(filer_cik) = 10),
    filer_name    TEXT NOT NULL,
    issuer_cik    TEXT CHECK (issuer_cik IS NULL OR length(issuer_cik) = 10),
    issuer_name   TEXT NOT NULL,
    cusip         TEXT NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    put_call      TEXT NOT NULL DEFAULT '',
    shares        NUMERIC,
    share_type    TEXT,                   -- SH | PRN
    value_usd     NUMERIC,                -- 13F only
    pct_class     NUMERIC,                -- 13D/13G only
    period        TEXT NOT NULL,          -- 13F quarter end; 13D/G event date
    filed         TEXT NOT NULL,
    resolved_how  TEXT,                   -- cusip map | 13D/G issuer | name | owner
    status        TEXT NOT NULL CHECK (status IN ('automatic', 'held', 'unresolved',
                                                  'dismissed', 'wrong')),
    check_note    TEXT,                   -- why held
    discovered_at TEXT NOT NULL,
    UNIQUE (source, accession, cusip, title, put_call)
);
CREATE INDEX fin_holding_filer ON fin_holding (filer_cik, period);
CREATE INDEX fin_holding_issuer ON fin_holding (issuer_cik, period);

-- CUSIP issuer (first 6 characters) → company: learned from 13D/G XML (issuerCik +
-- issuerCusipNumber) or mapped by the owner; cik NULL = dismissed (not a company we map).
CREATE TABLE fin_issuer_map (
    cusip6     TEXT PRIMARY KEY,
    cik        TEXT CHECK (cik IS NULL OR length(cik) = 10),
    name       TEXT,
    source     TEXT NOT NULL CHECK (source IN ('13D/G', 'owner')),
    mapped_by  TEXT,
    mapped_at  TEXT NOT NULL
);

-- Schedule 13D/13G headers read once (D-M02-45 (2)): who filed, about whom.
CREATE TABLE fin_schedule (
    accession    TEXT PRIMARY KEY,
    form         TEXT NOT NULL,
    filed        TEXT NOT NULL,
    filer_cik    TEXT,
    filer_name   TEXT,
    subject_cik  TEXT,
    subject_name TEXT,
    relevant     INTEGER NOT NULL DEFAULT 0, -- filer is ours, or both sides are known
    xml_read     INTEGER NOT NULL DEFAULT 0,
    detail       TEXT,
    read_at      TEXT NOT NULL
);

-- "wrong?" on a record: removed and kept out of later runs (D-M02-42).
CREATE TABLE fin_suppress (
    key        TEXT PRIMARY KEY,           -- source:filer_cik:cusip6 or text:<pair>:<kind>
    reason     TEXT,
    by_owner   TEXT,
    at         TEXT NOT NULL
);

-- Text passages naming a financing link (K1–K4, K6), like supply_link: A = the filer of
-- the document, B = the company it names. One m02_finlink item per pair and kind.
CREATE TABLE fin_text (
    text_id       INTEGER PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('K1', 'K2', 'K3', 'K4', 'K6')),
    a_cik         TEXT CHECK (a_cik IS NULL OR length(a_cik) = 10),
    a_name        TEXT NOT NULL,
    b_cik         TEXT CHECK (b_cik IS NULL OR length(b_cik) = 10),
    b_name        TEXT NOT NULL,
    direction     TEXT CHECK (direction IN ('a_to_b', 'b_to_a')),
    amount_usd    NUMERIC,
    instrument    TEXT,
    accession     TEXT NOT NULL,
    filename      TEXT NOT NULL,
    form          TEXT,
    filed         TEXT,
    quote         TEXT NOT NULL,
    quote_start   INTEGER NOT NULL,
    quote_end     INTEGER NOT NULL,
    how           TEXT NOT NULL,
    a_side        TEXT NOT NULL,
    b_side        TEXT NOT NULL,
    pair_key      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'candidate'
                  CHECK (status IN ('candidate', 'confirmed', 'rejected')),
    discovered_at TEXT NOT NULL,
    seen_at       TEXT,
    decided_at    TEXT,
    UNIQUE (accession, filename, quote_start, b_side)
);
CREATE INDEX fin_text_a ON fin_text (a_cik, status);
CREATE INDEX fin_text_b ON fin_text (b_cik, status);
CREATE INDEX fin_text_pair ON fin_text (pair_key, kind);

-- Targeted-search hit documents waiting to be fetched (D-M02-45 (4)).
CREATE TABLE fin_fetch (
    url          TEXT PRIMARY KEY,
    cik          TEXT,
    entity_name  TEXT,
    accession    TEXT NOT NULL,
    filename     TEXT NOT NULL,
    form         TEXT,
    file_date    TEXT,
    phrase       TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('queued', 'stored', 'failed')),
    detail       TEXT,
    queued_at    TEXT NOT NULL,
    done_at      TEXT
);
