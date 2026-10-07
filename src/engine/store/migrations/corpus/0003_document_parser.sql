-- Document text is derived from raw bytes by a versioned parser (M00_SEC_DATA rule 5),
-- so a parser change can re-run on stored raw responses (D-SEC-7).

ALTER TABLE document ADD COLUMN parser_version TEXT;
ALTER TABLE document ADD COLUMN encoding TEXT;
ALTER TABLE document ADD COLUMN raw_size INTEGER;
ALTER TABLE document ADD COLUMN description TEXT;
