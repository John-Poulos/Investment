-- M04 Part 7a unit and dimensional data (D-M04-42; M04_BUILD_LOG.md "Migrations").
-- Numbered 0035 (Part 3 = 0034); numbers after 0035 are taken in merge order, because the
-- migration runner requires 1..n with no gaps.

-- (1) Dimensional facts from a filing's XBRL instance (companyfacts keeps none): major
-- customers, business segments, products or services, classes of stock. One row per fact;
-- `axis` / `member` = the kept axis that classifies it (customer, then segment, then
-- product, then class of stock); `dims` = every axis=member pair of its context, sorted
-- and joined by ';' (e.g. a customer percentage also names its benchmark and risk type).
-- Values as filed: a later filing's different value for the same concept, dims and period
-- is a recast, flagged at read time, never merged (D-M04-42).
CREATE TABLE fact_dim (
    cik          TEXT NOT NULL CHECK (length(cik) = 10),
    accession    TEXT NOT NULL,
    form         TEXT,
    filed        TEXT NOT NULL,
    concept      TEXT NOT NULL,          -- prefix:tag, e.g. us-gaap:Revenues
    axis         TEXT NOT NULL,          -- e.g. srt:MajorCustomersAxis
    member       TEXT NOT NULL,          -- e.g. nvda:CustomerAMember
    dims         TEXT NOT NULL,          -- all axis=member pairs, sorted, ';'-joined
    period_start TEXT,                   -- NULL for instants
    period_end   TEXT NOT NULL,
    value        NUMERIC NOT NULL,
    unit         TEXT NOT NULL           -- USD, shares, pure, …
);
CREATE UNIQUE INDEX fact_dim_key
    ON fact_dim (accession, concept, dims, ifnull(period_start, ''), period_end, unit);
CREATE INDEX fact_dim_lookup ON fact_dim (cik, axis, concept, period_end);

-- (2) Unit KPIs and credits (Tesla DS2 extractor, EX-99.1/EX-99.2 releases, 10-K
-- sentences; S5.5–S5.7). Credits are their own rows (kind 'credit'), never netted into a
-- KPI; contribution margins are stored only when the company states them (kind
-- 'non_gaap'). `line` = model line or category as the company labels it ('' = total);
-- `period_label` is kept as stated, `period_end` is its mapped date.
CREATE TABLE unit_metric (
    cik          TEXT NOT NULL CHECK (length(cik) = 10),
    metric       TEXT NOT NULL,          -- deliveries, production, storage_deployed, …
    line         TEXT NOT NULL DEFAULT '',
    period_label TEXT NOT NULL,          -- Q4-2023, FY2023, 2019
    period_start TEXT,
    period_end   TEXT NOT NULL,
    value        NUMERIC NOT NULL,
    unit         TEXT NOT NULL,          -- vehicles, MWh, GWh, units, USD
    kind         TEXT NOT NULL CHECK (kind IN ('kpi', 'credit', 'non_gaap')),
    basis        TEXT NOT NULL,          -- stated | prior-year column | sum of 4 quarters
    source       TEXT NOT NULL,          -- EX-99.1 | EX-99.2 | 10-K | 10-Q
    accession    TEXT NOT NULL,
    filename     TEXT,
    filed        TEXT NOT NULL,
    quote        TEXT NOT NULL,          -- the row or sentence, verbatim
    extractor    TEXT NOT NULL,          -- tesla-ds2-1, sentence-1, release-table-1
    extracted_at TEXT NOT NULL,
    PRIMARY KEY (cik, metric, line, period_label, accession)
);
CREATE INDEX unit_metric_cik ON unit_metric (cik, metric, period_end);
