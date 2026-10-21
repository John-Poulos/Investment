-- M08 Part 2 analyst estimates (D-M08-6, D-M08-14; DS19; D-STO-31).
-- estimate_snapshot: one row per horizon row of an Alpha Vantage EARNINGS_ESTIMATES reply
-- (fiscal years and quarters, past quarters included), every vendor field stored from the
-- first snapshot (named columns as numbers, and the row as received in `raw`, so a field the
-- vendor adds later is kept too). NULL = the vendor sent null or no value: missing, never 0.
-- A fetch on the same Eastern date replaces that date's rows; older snapshots are kept (they
-- build the revision history past 90 days, deferred). The rotation's last attempt per
-- company (ok / no coverage / failed) lives in refresh_state `m08_estimates:<cik>`.
CREATE TABLE estimate_snapshot (
    cik            TEXT NOT NULL CHECK (length(cik) = 10),
    ticker         TEXT NOT NULL,
    snapshot_date  TEXT NOT NULL,         -- US Eastern date of the fetch
    horizon        TEXT NOT NULL,         -- vendor label as stated ("current fiscal year")
    period_end     TEXT NOT NULL,         -- vendor `date`: the period's end (fiscal mapping)
    eps_avg        REAL,
    eps_high       REAL,
    eps_low        REAL,
    eps_count      REAL,                  -- analysts in the EPS average
    eps_avg_7d     REAL,                  -- the average 7, 30, 60 and 90 days ago
    eps_avg_30d    REAL,
    eps_avg_60d    REAL,
    eps_avg_90d    REAL,
    rev_up_7d      REAL,                  -- EPS revisions up / down, trailing 7 and 30 days
    rev_down_7d    REAL,
    rev_up_30d     REAL,
    rev_down_30d   REAL,
    revenue_avg    REAL,
    revenue_high   REAL,
    revenue_low    REAL,
    revenue_count  REAL,
    raw            TEXT NOT NULL,         -- the vendor row as received (JSON)
    source_ref     TEXT NOT NULL,         -- the request as logged (no key)
    fetched_at     TEXT NOT NULL,         -- UTC
    PRIMARY KEY (cik, snapshot_date, horizon, period_end)
);
CREATE INDEX estimate_snapshot_cik_date ON estimate_snapshot (cik, snapshot_date);
