-- M02 part 5 live check 3 (D-M02-40): a precision-set passage the current rules no longer
-- produce stays (it is the answer key) but is marked stale, so it raises no review item and
-- is not shown on the company tab.
ALTER TABLE supply_link ADD COLUMN stale INTEGER NOT NULL DEFAULT 0;
