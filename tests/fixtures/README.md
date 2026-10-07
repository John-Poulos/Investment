# Test fixtures

Byte-exact (`tests/fixtures/** -text` in .gitattributes).

| File | Origin |
|---|---|
| sec/company_tickers_exchange.json | Synthetic subset in SEC's format |
| sec/company_tickers.json | Synthetic subset in SEC's format; MU row deliberately conflicts |
| sec/submissions_CIK0000320193.json | Synthetic, trimmed submissions JSON |
| sec/throttle_page.html | Synthetic; replace with a recorded block page if one is ever received |

Replace synthetic files with recorded responses once the live tests have run.
