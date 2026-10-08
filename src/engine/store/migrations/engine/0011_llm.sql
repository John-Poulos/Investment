-- Grounded LLM runs (M00_SEARCH D-SRCH-17/18/19). Every call is owner-initiated and logged
-- with model, prompt version, tokens, cost estimate and raw response. Observations are
-- labeled interpretations; each cites stored text by accession, file, offsets and exact quote
-- (survives a corpus rebuild). Rejected observations are kept with the reason, never as fact.

CREATE TABLE llm_call (
    call_id        INTEGER PRIMARY KEY,
    use_case       TEXT NOT NULL,          -- e.g. guidance_reasons
    cik            TEXT CHECK (cik IS NULL OR length(cik) = 10),
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    input_hash     TEXT NOT NULL,          -- sha256 of system + user prompt (cache key)
    request        TEXT NOT NULL,          -- the exact prompt sent
    response       TEXT,                   -- raw model text
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    thought_tokens INTEGER,
    cost_usd       NUMERIC,                -- from config prices and reported tokens
    status         TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    error          TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX llm_call_cache ON llm_call (use_case, model, prompt_version, input_hash, status);

CREATE TABLE llm_observation (
    obs_id     INTEGER PRIMARY KEY,
    call_id    INTEGER NOT NULL REFERENCES llm_call (call_id) ON DELETE CASCADE,
    cik        TEXT CHECK (cik IS NULL OR length(cik) = 10),
    use_case   TEXT NOT NULL,
    subject    TEXT NOT NULL,              -- JSON: what the observation is about (e.g. a change)
    claim      TEXT NOT NULL,              -- the model's statement (an interpretation)
    verified   INTEGER NOT NULL CHECK (verified IN (0, 1)),
    detail     TEXT,                       -- why verification failed, if it did
    created_at TEXT NOT NULL
);
CREATE INDEX llm_observation_call ON llm_observation (call_id);

CREATE TABLE llm_citation (
    citation_id  INTEGER PRIMARY KEY,
    obs_id       INTEGER NOT NULL REFERENCES llm_observation (obs_id) ON DELETE CASCADE,
    accession    TEXT NOT NULL,
    filename     TEXT NOT NULL,
    passage_id   INTEGER,                  -- corpus passage at the time of the call
    start_offset INTEGER NOT NULL,         -- passage offsets into corpus document.text
    end_offset   INTEGER NOT NULL,
    quote        TEXT NOT NULL,            -- the model's verbatim quote (checked)
    doc_sha256   TEXT NOT NULL
);
CREATE INDEX llm_citation_obs ON llm_citation (obs_id);
