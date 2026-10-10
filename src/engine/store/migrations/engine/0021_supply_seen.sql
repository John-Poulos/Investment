-- M02 part 5 live check 1: re-reading stored documents after a rule change (D-M02-37).
-- seen_at = the last run that produced the passage; an undecided passage the current
-- rules no longer produce is removed, while discovered_at (first seen) is kept for the
-- passages that remain.
ALTER TABLE supply_link ADD COLUMN seen_at TEXT;
UPDATE supply_link SET seen_at = discovered_at;
