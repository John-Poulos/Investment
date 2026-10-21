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
| m04/* | Hand-built from real figures in the M04 docs (companyconcept files, R1 cover pages); sources and placeholders per file in m04/README.md |
| m07/huang_nvda_0001045810-25-000143.xml | Reconstruction in the layout of Huang's real Form 4 (M07 pack, S-new-M07-18): F row 06-18 40,163 at $144.12, direct line 75,773,225 after it; 7 S rows on 06-20/06-23, 100,000 shares, $14,403,585 (row prices reconstructed to that total), footnote F3 plan; 8 indirect holding lines totalling 783,375,400 (names and split reconstructed); aff10b5One = 1 |
| m07/musk_tsla_0001104659-25-089693.xml | Reconstruction of Musk's Form 4: 25 P rows on 2025-09-12 by trust, 2,568,732 shares, prices $371.90–$396.36 (row prices reconstructed to ≈ $999.96M), trust 413,362,808 after, direct holding 96,000,000; aff10b5One = 0 |
| m07/tan_intc_0001127602-25-010360.xml | Reconstruction of Tan's Form 4: code A, 1,043,406 shares at $23.96 by family trust; the offer-letter footnote wording and the owner CIK are reconstructed |
| m07/amend_original.xml, m07/amend_4a.xml | Synthetic 4 / 4/A pair (issuer 0000000042): non-plan S 5,000 at $50.00 + gift; the 4/A corrects the price to $51.00 |
| m07/13f/brk_2024q1_{index.htm,primary_doc.xml,infotable.xml} | Reconstruction in EDGAR's 13F-HR layout (filing index with the XSL rendering rows, cover page, information table) of Berkshire's 13F-HR for 2024-03-31, 0000950123-24-005622 filed 2024-05-15 (M07 pack, S243): AAPL 789,368,450 shares, $135,360,901,805, split over 12 rows (other-manager combinations; the split is reconstructed); 5 rows of companies that are not ours (BAC, AXP, KO, CVX, OXY; values and shares reconstructed); `tableValueTotal` = the row sum |
| m07/13f/brk_2024q2_{…} | Same for 2024-06-30, 0000950123-24-008740 filed 2024-08-14: AAPL 400,000,000 shares, $84,248,000,000 over 12 rows (pack); other rows reconstructed |
| m07/13f/brk_2022q3_{…} | Synthetic pre-2023 filing in the same layout: 2022-09-30, accession 0000950123-22-099901 (**invented**), filed 2022-11-14, values in **thousands** (AAPL 894,802,319 shares, $123,661,680 thousand) |
| (generated in tests/test_ownership_managers.py) | A Duquesne-style manager (fictional CIK 0009999901): NVDA across the 2024 10:1 split, a CALL row, GOOG class A + C, MSFT new, an ambiguous issuer name, a missing quarter, RESTATEMENT and NEW HOLDINGS amendments |
| m08/* | M08 Part 1: MU fiscal years and the pack's closes at its 10-K dates; synthetic NVDA, INFQ, MSTR and D32 cases generated in tests/test_valuation.py; sources and placeholders per file in m08/README.md |

Replace synthetic files with recorded responses once the live tests have run.
