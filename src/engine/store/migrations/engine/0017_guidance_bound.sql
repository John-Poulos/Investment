-- Live check of M02 part 4 (D-M02-23): spoken guidance is often a bound, not a point
-- ("more than $25 billion", "over $50 billion", "up to ..."). The value is stored in
-- low = high as stated, with its bound; it is never shown as a point.

ALTER TABLE guidance ADD COLUMN bound TEXT CHECK (bound IN ('floor', 'ceiling'));
