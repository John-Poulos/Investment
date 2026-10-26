-- M06 Part 1: owner moat verdicts (docs/M06_MOAT.md rules 2 and 4; D-M06-3…6, -8;
-- D-M06-9…; D-STO-33).
-- Append-only: every entry is a new row, so the history (and Part 2's "owner downgrade")
-- is kept. The company's current verdict is its newest row with status 'active'. An entry
-- whose cited quote is not found in the stored filing text is stored with status 'rejected'
-- and never applies (D21). N_A is never entered here: it comes from the model tags
-- (`config/company_models.toml`) or the SEC industry code, and is written by the M06 pass.
-- The D13 rows `moat_verdict` and `moat_gate` are written to `signal` from these rows.
CREATE TABLE m06_verdict (
    verdict_id      INTEGER PRIMARY KEY,
    cik             TEXT NOT NULL CHECK (length(cik) = 10),
    verdict         TEXT NOT NULL CHECK (verdict IN ('WIDE', 'NARROW', 'NONE', 'UNRATED')),
    sources         TEXT,                  -- source labels, comma-separated (D-M06-4)
    band            TEXT CHECK (band IS NULL OR band IN ('le3', '3to5', '5to10', 'gt10')),
    reason          TEXT NOT NULL,
    passage_ref     TEXT,                  -- <accession>/<filename>[#p<passage_id>] of a cited quote
    quote           TEXT,                  -- the owner's quote, as entered
    quote_status    TEXT CHECK (quote_status IS NULL OR quote_status IN ('verified', 'rejected')),
    grade           TEXT NOT NULL CHECK (grade IN ('A', 'B')),
    override        TEXT CHECK (override IS NULL OR override IN ('met', 'not_met')),
    override_reason TEXT,
    quant_class     TEXT,                  -- `moat_quant` class seen at entry (re-open rule)
    quant_fy        TEXT,                  -- newest fiscal year of the quant window at entry
    proposal        TEXT,                  -- the engine's proposal shown at entry
    item_id         INTEGER,               -- the m06_verdict review item closed by this entry
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'rejected')),
    decided_by      TEXT NOT NULL,
    decided_at      TEXT NOT NULL,         -- UTC timestamp of the entry; never back-dated
    as_of           TEXT NOT NULL,         -- date the verdict applies from (= decided date)
    CHECK (override IS NULL OR length(trim(override_reason)) > 0)
);
CREATE INDEX m06_verdict_cik ON m06_verdict (cik, decided_at);
