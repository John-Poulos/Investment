-- M04 Part 6 earnings quality (D-M04-14, -17, -18, -19, -20, -90…93; D-STO-27;
-- M04_BUILD_LOG.md "Migrations"). Scores (CFO/NI, accruals, M-score, misstatement score,
-- contract gaps) are computed from stored facts on every pass and written as signals; only
-- the text findings, which carry quotes and owner answers, are stored here.

-- (1) Estimate changes (D-M04-17, -18): one row per sentence of a stored annual report
-- that states the effect of a change in estimate with an amount, keyed by filing version
-- (accession + sentence offset), so an amount a later report restates (GE 2016: $2.2B →
-- $0.7B) is a new row and the earlier one is kept. `amount` is signed: + raises income.
-- `basis`: after_tax (÷ net income), pre_tax (÷ operating income, else pretax income from
-- continuing operations), expense (pre-tax, sign of the income effect). `band`: note
-- (< 10%), watch (10–25%), elevated (≥ 25%), not_meaningful (denominator ≤ 0 or below 1%
-- of revenue), missing (no denominator stored). `baseline` = found by the company's first
-- scan (D-M04-71: queued only when filed in the last 12 months).
CREATE TABLE estimate_change (
    cik              TEXT NOT NULL CHECK (length(cik) = 10),
    accession        TEXT NOT NULL,
    start_offset     INTEGER NOT NULL,      -- sentence start in document.text
    doc_ref          TEXT NOT NULL,         -- accession/filename
    form             TEXT,
    filed            TEXT,
    fiscal_label     TEXT,                  -- the year the amount is for (FY2016)
    period_end       TEXT,
    kind             TEXT NOT NULL,         -- useful_life | catch_up | contract | other
    amount           NUMERIC NOT NULL,
    basis            TEXT NOT NULL CHECK (basis IN ('after_tax', 'pre_tax', 'expense')),
    denominator      NUMERIC,
    denominator_what TEXT,                  -- concept, tag and accession of the denominator
    share            NUMERIC,               -- amount ÷ denominator (signed)
    band             TEXT NOT NULL CHECK (band IN ('note', 'watch', 'elevated',
                                                   'not_meaningful', 'missing')),
    quote            TEXT NOT NULL,
    passage_id       INTEGER,
    baseline         INTEGER NOT NULL DEFAULT 0,
    item_id          INTEGER,
    owner_outcome    TEXT,                  -- the owner's answer on the m04_estimate item
    owner_at         TEXT,
    first_seen_at    TEXT NOT NULL,
    computed_at      TEXT NOT NULL,
    PRIMARY KEY (cik, accession, start_offset)
);
CREATE INDEX estimate_change_cik ON estimate_change (cik, filed);

-- (2) Recurring "one-time" charges (D-M04-19): one row per fiscal year and finding —
-- a restructuring, impairment or write-down tag (`source` = 'tag', `what` = concept,
-- `amount` in $) or "non-recurring"/"one-time" wording in that year's stored annual
-- report (`source` = 'text', `what` = the phrase, `quote` = the sentence). The non-GAAP
-- gap is quoted on the tab from the company's release, never computed or stored here.
CREATE TABLE special_item (
    cik          TEXT NOT NULL CHECK (length(cik) = 10),
    period_end   TEXT NOT NULL,             -- fiscal year end
    fiscal_label TEXT NOT NULL,
    source       TEXT NOT NULL CHECK (source IN ('tag', 'text')),
    what         TEXT NOT NULL,
    accession    TEXT NOT NULL,
    amount       NUMERIC,
    quote        TEXT,
    computed_at  TEXT NOT NULL,
    PRIMARY KEY (cik, period_end, source, what, accession)
);
