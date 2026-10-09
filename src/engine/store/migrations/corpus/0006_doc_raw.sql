-- Raw bytes of documents that do not come from SEC (M02 D-M02-20): an Alpha Vantage
-- transcript reply (JSON) or a company IR file the owner downloaded (PDF). Stored once,
-- so the text, sections and guidance can be rebuilt locally without another request.

CREATE TABLE doc_raw (
    doc_id        INTEGER PRIMARY KEY REFERENCES document (doc_id) ON DELETE CASCADE,
    source        TEXT NOT NULL CHECK (source IN ('alpha_vantage', 'ir_download')),
    symbol        TEXT NOT NULL,
    quarter       TEXT NOT NULL,
    original_name TEXT,
    body          BLOB NOT NULL,
    sha256        TEXT NOT NULL,
    fetched_at    TEXT NOT NULL
);
