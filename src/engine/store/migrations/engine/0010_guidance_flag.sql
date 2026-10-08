-- Guidance quality flag (D-SRCH-15, owner 2026-10-08): ratio guidance on a near-zero base
-- (e.g. Intel GAAP tax rate 476%) is stored as stated but flagged 'not_meaningful';
-- flagged rows are shown with their reason and excluded from guidance-vs-actual scoring
-- and from LLM trend input. Nothing is deleted.

ALTER TABLE guidance ADD COLUMN flag TEXT CHECK (flag IN ('not_meaningful'));
ALTER TABLE guidance ADD COLUMN flag_reason TEXT;
