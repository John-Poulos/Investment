-- M02 part 5, supplier discovery rungs L0–L3 (D-M02-7, D-M02-9, D-M02-35).

-- One row per passage tying two companies. Party A is the filer of the document; party B
-- is the company it names. direction: a_to_b = A supplies B (L2: a supplier names its
-- customer), b_to_a = B supplies A (L1: a customer names its supplier), NULL = not stated
-- (L3 contracts) until Gemini or the owner says. Names are kept as written; ciks only when
-- the name resolves (foreign suppliers often have none).
CREATE TABLE supply_link (
    link_id        INTEGER PRIMARY KEY,
    rung           TEXT NOT NULL CHECK (rung IN ('L1', 'L2', 'L3')),
    grade          TEXT NOT NULL CHECK (grade IN ('A', 'B', 'C')),
    a_cik          TEXT CHECK (a_cik IS NULL OR length(a_cik) = 10),
    a_name         TEXT NOT NULL,
    b_cik          TEXT CHECK (b_cik IS NULL OR length(b_cik) = 10),
    b_name         TEXT NOT NULL,
    direction      TEXT CHECK (direction IN ('a_to_b', 'b_to_a')),
    share_pct      NUMERIC,            -- revenue share stated in the passage, if any
    accession      TEXT NOT NULL,
    filename       TEXT NOT NULL,
    form           TEXT,
    filed          TEXT,
    quote          TEXT NOT NULL,
    quote_start    INTEGER NOT NULL,
    quote_end      INTEGER NOT NULL,
    how            TEXT NOT NULL,      -- the rule or search phrase that found it
    a_side         TEXT NOT NULL,      -- company identity: cik, else key:<aliases key>, else
    b_side         TEXT NOT NULL,      -- name:<as written>
    pair_key       TEXT NOT NULL,      -- unordered company pair: one review item per pair
    llm_type       TEXT,               -- Gemini label (use case 5): supply | partner | ...
    llm_direction  TEXT,               -- a_to_b | b_to_a | unclear
    llm_call_id    INTEGER,
    status         TEXT NOT NULL DEFAULT 'candidate'
                   CHECK (status IN ('candidate', 'confirmed', 'rejected')),
    item_id        INTEGER,
    discovered_at  TEXT NOT NULL,      -- point-in-time backtests (D-M02-15)
    decided_at     TEXT,
    UNIQUE (accession, filename, quote_start, a_name, b_name)
);
CREATE INDEX supply_link_a ON supply_link (a_cik, status);
CREATE INDEX supply_link_b ON supply_link (b_cik, status);
CREATE INDEX supply_link_pair ON supply_link (pair_key);

-- L0: input categories a company depends on, quoted from its own Item 1/1A (Gemini use
-- case 5b, owner-initiated; grade C until a named link exists).
CREATE TABLE input_category (
    input_id     INTEGER PRIMARY KEY,
    cik          TEXT NOT NULL CHECK (length(cik) = 10),
    category     TEXT NOT NULL,
    quote        TEXT NOT NULL,
    accession    TEXT NOT NULL,
    filename     TEXT NOT NULL,
    quote_start  INTEGER NOT NULL,
    quote_end    INTEGER NOT NULL,
    llm_call_id  INTEGER,
    status       TEXT NOT NULL DEFAULT 'candidate'
                 CHECK (status IN ('candidate', 'confirmed', 'rejected')),
    item_id      INTEGER,
    discovered_at TEXT NOT NULL,
    UNIQUE (cik, category)
);

-- Owner's blind labels for the precision set (D-M02-9, D-M02-35): judged from the passage
-- text only. Party A / B as in supply_link.
CREATE TABLE link_gold (
    gold_id      INTEGER PRIMARY KEY,
    link_id      INTEGER NOT NULL UNIQUE REFERENCES supply_link (link_id),
    position     INTEGER NOT NULL,   -- order shown (1..n)
    gold_type    TEXT CHECK (gold_type IN ('supply', 'partner', 'competitor', 'none',
                                           'unclear')),
    gold_direction TEXT CHECK (gold_direction IN ('a_to_b', 'b_to_a', 'unclear')),
    labelled_by  TEXT,
    labelled_at  TEXT
);

-- L2 hit documents waiting to be fetched (per-run cap), and what found them.
CREATE TABLE supply_fetch (
    url          TEXT PRIMARY KEY,
    cik          TEXT,
    entity_name  TEXT,
    accession    TEXT NOT NULL,
    filename     TEXT NOT NULL,
    form         TEXT,
    file_date    TEXT,
    customer_key TEXT NOT NULL,      -- aliases.toml key of the customer searched for
    phrase       TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('queued', 'stored', 'failed')),
    detail       TEXT,
    queued_at    TEXT NOT NULL,
    done_at      TEXT
);
