-- M04 Part 1c company profile, review queue and peer shortlist (D-M04-4, -7, -8, -12, -46,
-- -71; M04_BUILD_LOG.md "Migrations"). Model tags live in config/company_models.toml (the
-- app never writes them, D-M04-8), so they need no table.

-- (1) Life-cycle stage per company and fiscal year (D-M04-7, -12). `computed` is the
-- Dickinson stage that holds in 2 of the last 3 fiscal years on core investing (NULL when
-- none holds or history is short); `reasons` lists why it goes to review (JSON). The
-- owner's confirmation is stored on the row of the fiscal year it answered; the latest
-- confirmation routes until the owner changes it.
CREATE TABLE company_stage (
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    period_end     TEXT NOT NULL,          -- latest fiscal year end in the 3-year window
    fiscal_label   TEXT NOT NULL,          -- FY2025
    computed       TEXT CHECK (computed IS NULL OR computed IN
                       ('introduction', 'growth', 'mature', 'shake_out', 'decline')),
    years          TEXT NOT NULL,          -- JSON: per year signs and stage, core and total
    rev_cagr3      NUMERIC,                -- NULL = missing (reason in `method`)
    reasons        TEXT NOT NULL,          -- JSON list of review reasons
    method         TEXT NOT NULL,          -- inputs, missing terms, total-investing note
    confirmed      TEXT CHECK (confirmed IS NULL OR confirmed IN
                       ('introduction', 'growth', 'mature', 'shake_out', 'decline')),
    confirmed_by   TEXT,
    confirmed_at   TEXT,
    item_id        INTEGER REFERENCES review_queue (item_id),
    computed_at    TEXT NOT NULL,
    PRIMARY KEY (cik, period_end)
);

-- (2) M04 proposals in the review queue (as `m02_proposal`, D-M02-18), plus the D-M04-71
-- priority group, the baseline marker and whether the item counts against the weekly cap
-- of 5. Status 'baseline' = recorded and shown, never queued.
CREATE TABLE m04_proposal (
    prop_key      TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    cik           TEXT,
    reason        TEXT NOT NULL,
    payload       TEXT,                    -- JSON
    priority      INTEGER NOT NULL,        -- 0 setup/operational/alert, 1–7 per D-M04-71
    capped        INTEGER NOT NULL CHECK (capped IN (0, 1)),
    baseline      INTEGER NOT NULL DEFAULT 0 CHECK (baseline IN (0, 1)),
    status        TEXT NOT NULL CHECK (status IN ('queued', 'overflow', 'baseline')),
    item_id       INTEGER REFERENCES review_queue (item_id),
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    owner_id      TEXT NOT NULL DEFAULT 'owner'
);
CREATE INDEX m04_proposal_status ON m04_proposal (status, priority, first_seen_at);

-- (3) Ranked peer shortlist per target company (D-M04-4, S6.2). A SIC candidate comes
-- from browse-by-SIC and the stored form indexes (active = a 10-K, 20-F or 40-F in the
-- last 12 months); an owner-added peer may sit outside the SIC; a non-SEC peer has no CIK
-- and is stored by name ("missing: not an SEC filer"). Confirmed sets go to
-- `peer_group` / `peer_member` (0001).
CREATE TABLE peer_candidate (
    target_cik     TEXT NOT NULL CHECK (length(target_cik) = 10),
    candidate_cik  TEXT CHECK (candidate_cik IS NULL OR length(candidate_cik) = 10),
    name           TEXT NOT NULL,
    sic            TEXT,
    rank           INTEGER,                -- 1 = closest revenue; NULL for owner additions
    active_forms   TEXT,                   -- e.g. "10-K 2026-02-20" or "20-F 2026-03-14"
    revenue        NUMERIC,                -- ranking revenue (USD), NULL = missing
    revenue_ref    TEXT,                   -- frame, tag, accession
    source         TEXT NOT NULL CHECK (source IN ('sic', 'owner', 'owner_name')),
    status         TEXT NOT NULL CHECK (status IN ('proposed', 'struck', 'confirmed')),
    added_at       TEXT NOT NULL,
    decided_at     TEXT,
    UNIQUE (target_cik, candidate_cik),
    UNIQUE (target_cik, name)
);

-- (4) Browse-by-SIC listing (S162; S1 re-probe, SB.17): companies EDGAR lists under a SIC,
-- per form type browsed. Replaced as a whole per SIC on each `run_financials.py profile`.
CREATE TABLE sic_listing (
    sic         TEXT NOT NULL,
    cik         TEXT NOT NULL CHECK (length(cik) = 10),
    name        TEXT NOT NULL,
    browsed     TEXT NOT NULL,             -- form type browsed: 10-K | 20-F | 40-F
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (sic, cik, browsed)
);
CREATE TABLE sic_browse (
    sic         TEXT NOT NULL,
    browsed     TEXT NOT NULL,
    pages       INTEGER NOT NULL,
    listed      INTEGER NOT NULL,
    capped      INTEGER NOT NULL CHECK (capped IN (0, 1)),  -- page cap reached: list partial
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (sic, browsed)
);
