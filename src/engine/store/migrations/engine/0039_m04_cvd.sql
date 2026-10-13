-- M04 Part 8a CvD assembly (D-M04-56, -68, -100…; D-STO-29; M04_BUILD_LOG.md "Migrations").
-- The CvD grid, its state, confidence and coverage, the health vote and the M01 reading are
-- computed from stored facts on every pass and written as D13 signals (`cvd_state`, …);
-- the owner's `m04_cvd` answers and the last pass's summary line live in `refresh_state`
-- (`m04_cvd:<cik>`, `m04_cvd_line:<cik>`). The only new table holds the owner's
-- market-share entries, which no filing carries.

-- Market share (D-M04-68; DS16): owner-entered third-party share (grade B) or a share the
-- owner computed from an industry total stated in a filing (grade A, the filing named in
-- `source`). One row per company, market and period; Q2's share row compares the latest
-- entry with one about 4 quarters earlier (300–430 days) in the same market: "falling" =
-- down ≥ 1 pp† in a flat or growing market (`market_size` when entered). Rows are never
-- deleted: a wrong entry is 'withdrawn' (who and when kept).
CREATE TABLE market_share (
    share_id     INTEGER PRIMARY KEY,
    cik          TEXT NOT NULL CHECK (length(cik) = 10),
    period_end   TEXT NOT NULL,          -- YYYY-MM-DD the share is measured for
    share_pct    NUMERIC NOT NULL CHECK (share_pct >= 0 AND share_pct <= 100),
    market       TEXT NOT NULL,          -- e.g. "DRAM revenue", "x86 server CPUs (units)"
    market_size  NUMERIC CHECK (market_size IS NULL OR market_size > 0),  -- optional, USD
    source       TEXT NOT NULL,          -- publisher and report, or the filing for grade A
    source_url   TEXT,
    grade        TEXT NOT NULL CHECK (grade IN ('A', 'B')),  -- D-M04-9, -68
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'withdrawn')),
    note         TEXT,
    entered_by   TEXT NOT NULL,
    entered_at   TEXT NOT NULL,
    withdrawn_by TEXT,
    withdrawn_at TEXT
);
CREATE INDEX market_share_cik ON market_share (cik, market, period_end);
