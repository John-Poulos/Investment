# Test fixtures

Byte-exact (`tests/fixtures/** -text` in .gitattributes).

| File | Origin |
|---|---|
| sec/company_tickers_exchange.json | Synthetic subset in SEC's format |
| sec/company_tickers.json | Synthetic subset in SEC's format; MU row deliberately conflicts |
| sec/submissions_CIK0000320193.json | Synthetic, trimmed submissions JSON |
| sec/submissions_CIK0000000042.json | Synthetic company with recent filings (10-Q, 8-K 2.02, 8-K 5.02, 10-K, Form 4) and one older page |
| sec/CIK0000000042-submissions-001.json | Synthetic older page (10-Q, 10-K/A), top-level arrays as SEC serves them |
| sec/throttle_page.html | Synthetic; replace with a recorded block page if one is ever received |

Replace synthetic files with recorded responses once the live tests have run.
