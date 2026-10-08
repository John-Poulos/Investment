-- Daily prices (M00_UI DS8, D-UI-2): Tiingo end-of-day bars, raw and adjusted, plus the
-- dividend and split that adjust them. One row per symbol and trading day. Missing days
-- stay missing (never filled). Licence: internal use only (S68).

CREATE TABLE price_bar (
    symbol       TEXT NOT NULL,          -- Tiingo symbol (watchlist ticker)
    date         TEXT NOT NULL,          -- trading day, YYYY-MM-DD
    open         NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC, volume NUMERIC,
    adj_open     NUMERIC, adj_high NUMERIC, adj_low NUMERIC, adj_close NUMERIC, adj_volume NUMERIC,
    div_cash     NUMERIC,
    split_factor NUMERIC,
    source       TEXT NOT NULL,          -- tiingo
    fetched_at   TEXT NOT NULL,
    PRIMARY KEY (symbol, date)
);

-- Per-symbol fetch state: what is stored and how the last fetch went.
CREATE TABLE price_fetch (
    symbol          TEXT PRIMARY KEY,
    cik             TEXT CHECK (cik IS NULL OR length(cik) = 10),
    first_date      TEXT,
    last_date       TEXT,
    bars            INTEGER NOT NULL DEFAULT 0,
    last_fetched_at TEXT,
    last_outcome    TEXT,                -- ok | not_found | failed | throttled | budget
    detail          TEXT,
    full_fetched_at TEXT                 -- last full-history fetch (first fetch, or after a split/dividend)
);
