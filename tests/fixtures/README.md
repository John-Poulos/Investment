# Test fixtures

Byte-exact (`tests/fixtures/** -text` in .gitattributes).

| File | Origin |
|---|---|
| sec/company_tickers_exchange.json | Synthetic subset in SEC's format |
| sec/company_tickers.json | Synthetic subset in SEC's format; MU row deliberately conflicts |
| sec/submissions_CIK0000320193.json | Synthetic, trimmed submissions JSON |
| sec/submissions_CIK0000000042.json | Synthetic company with recent filings (10-Q, 8-K 2.02, 8-K 5.02, 10-K, Form 4) and one older page |
| sec/CIK0000000042-submissions-001.json | Synthetic older page (10-Q, 10-K/A), top-level arrays as SEC serves them |
| sec/filing/0000000042-26-000004-index.htm | Synthetic filing index in SEC's -index.htm layout (viewer link, blank seq/type row, Data Files table) |
| sec/filing/xsem-8k_20260730.htm | Synthetic iXBRL 8-K (hidden ix:header, script, entities) |
| sec/filing/ex99-1.htm | Synthetic EX-99.1 with a table |
| sec/form4/new_10b51_checkbox.xml | Synthetic 2023+ Form 4: aff10b5One checkbox set, CEO sale with weighted-average price footnote |
| sec/form4/old_footnote_latin1.xml | Synthetic pre-2023 Form 4 in ISO-8859-1: 10b5-1 only in a footnote on the sale; purchase without footnote |
| sec/form4/joint_gift_exercise.xml | Synthetic 4/A joint filing (two owners), gift without price, option exercise, a holding row |
| sec/form_idx_sample.idx | Synthetic quarterly form.idx in EDGAR's fixed-width layout (10-K/A, co-registrants, SC 13D, Form 4) |
| sec/throttle_page.html | Synthetic; replace with a recorded block page if one is ever received |

Replace synthetic files with recorded responses once the live tests have run.
