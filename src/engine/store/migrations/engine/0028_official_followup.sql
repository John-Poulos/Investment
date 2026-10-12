-- M02 part 7b follow-up (D-M02-61, owner answers after live check 1).

-- (4) Federal Register: 1 = the theme phrase is in the document's title or abstract,
-- 0 = only in the body (passing mention), NULL = not checked yet (filled on the next run).
ALTER TABLE official_theme ADD COLUMN prominent INTEGER CHECK (prominent IN (0, 1));

-- (1) Enacted bills enter the weekly news item in the week the engine first saw them enacted.
ALTER TABLE congress_bill ADD COLUMN enacted_seen_at TEXT;
UPDATE congress_bill SET enacted_seen_at = updated_at WHERE status = 'enacted';

-- (2) arXiv counts now search title and abstract only; counts made with `all:` (authors,
-- comments too) are not comparable, so they are cleared and counted again.
DELETE FROM arxiv_count;
