# Round 3 — Known gaps check (dilution and financing pressure)

Read 2026-10-12. Scope: the 11 "Round 3" bullets in `docs/M04_DESIGN_PACK.md` Known gaps (lines 3511–3521). No SEC host was requested. Non-SEC hosts used: Boeing's newsroom, Intel's IR site (intc.com, which re-hosts Intel's filings), Infleqtion's IR site, law-firm pages and the press.

## Summary
| # | Gap | Status | Changes pack? |
|---|---|---|---|
| 1 | SPCX lock-up terms | partly closed | yes (field shape) |
| 2 | SPCX preferred-to-common count | needs owner data | no |
| 3 | Intel 60M gap; 424B7 holder | closed | yes |
| 4 | BA over-allotment | closed | yes |
| 5 | INFQ CY2025/CY2024 frame pair | needs owner data | no |
| 6 | Review volumes; MSTR instruments; INTC "downgraded" | partly closed | yes |
| 7 | Up-C example | partly closed | no |
| 8 | Blank checks in the frame; SIC 6770 path | partly closed | yes (S3.2 data path) |
| 9 | AMZN/GOOG 424B5s are debt | partly closed | no |
| 10 | S-new-68 in Round 6 | not a gap any more | no |
| 11 | Pack-level critique slices | stays open (owner: consolidation step) | no |

## Findings

**1. SPCX lock-up (partly closed).**
- Press summaries of the prospectus describe a staggered lock-up, not one end date:
  - 20% of holdings is released after the Q2 report, plus 10% more on a price trigger;
  - 7% each at days 70, 90, 105, 120 and 135;
  - 28% after the Q3 report;
  - everything after day 180 (about 2026-12-09 from the 2026-06-12 IPO).
- Musk and "certain significant investors" are locked for 366 days.
- Sources (secondary; they disagree on the final date): fool.com 2026-07-01 and 2026-06-11; qz.com; nasdaq.com; fortune.com 2026-07-03; darrowwealthmanagement.com.
- **Pack effect.** S3.5 says "424B4: IPO, with the lock-up end read from text". A single date cannot hold this structure. Store a release schedule instead: rows of (trigger: date or earnings event or price condition, % of holdings, holder group). Resale supply is then shown per tranche.
- Probe: see P1.

**2. SPCX preferred-to-common count (needs owner data).**
- No non-SEC copy was found.
- No clean ratio links 6,728M to the XBRL counts (6,728 ÷ 2,046 = 3.29; ÷ 1,911 converted in Q1 = 3.52; the split is 5). The X and xAI share exchanges may sit in the same equity-table rows. Not guessed.
- The figure is not used in any computation (the 4.85% new-money figure and the +100.2% stand), so the pack is unchanged.
- Probe: P2.

**3. Intel (closed).**
- **60M gap.** The Q2 2026 10-Q EPS note (Note 4), read on Intel's IR host:
  - 143M escrowed shares were not yet released at 2026-06-27;
  - 71M of them count as "not contingently issuable" and are **included in basic EPS**;
  - the other 71M are excluded until the Department of Commerce's Secure Enclave disbursements arrive;
  - 7M were released in Q2 and 13M in H1 2026;
  - basic weighted average was 5,104M (Q2) and 5,108M (H1).
- Unreleased escrow is not in the cover count. Arithmetic check:
  - 4,377 + 274.6 + 87.0 = 4,738.6M, against the 2025-10-17 cover of 4,770M;
  - with the 158.7M escrow added it would be 4,897M, far above the cover.
- Cover 5,044M + 71M = 5,115M, against 5,104M weighted. The −11M residual is timing within the quarter.
- So the gap is the escrow, now confirmed. Source: https://www.intc.com/filings-reports/all-sec-filings/xbrl_doc_only/4350
- **424B7 of 2025-09-05.** It registers resale by the US Department of Commerce of the warrant and up to 673,839,150 shares:
  - 433,323,000 "New Shares" already issued, which includes the escrow tranche;
  - 240,516,150 warrant shares.
  - No proceeds to Intel. Source: Exhibit 5.1 opinion on intc.com, https://www.intc.com/filings-reports/all-sec-filings/content/0000050863-25-000147/a09052025ex51opinion.htm
  - A January 2026 re-filing under a new shelf (8-K 0000050863-26-000031) is reported by search results only (secondary).
- **Pack effect:**
  - Intel "Check" row: replace "cause not checked" with "71M escrowed shares in basic EPS but not outstanding (10-Q Note 4)".
  - S3.6 should list the 71M contingently issuable escrow shares beside the contingent warrant.
  - The cover-vs-weighted cross-check (failure-mode row) needs an "escrow/contingently returnable" cause label.
  - Resale row: "DOC resale of 673.8M shares incl. warrant shares; no new shares".
- **Cross-round note for Round 2:**
  - Intel recognised $12.5B (Q2 2026) and $13.6B (H1 2026) of fair-value losses on the escrowed shares;
  - the escrowed-shares derivative liability rose from $2.7B to $15.6B;
  - this is a large non-operating item for the earnings-quality checks.

**4. Boeing over-allotment (closed).**
- Boeing's 2024-10-29 pricing release offered:
  - 100,000,000 depositary shares plus a 15,000,000 option ($750M);
  - 112,500,000 common shares plus a 16,875,000 option.
  - Source: https://boeing.mediaroom.com/2024-10-29-Boeing-Announces-Pricing-of-Upsized-Concurrent-Offerings-of-Common-Stock-and-Depositary-Shares
- Exercise in full is reported for the depositary option (search summary of Boeing's 8-K, secondary). The pack's own XBRL figures prove it:
  - FY2024 convertible-preferred proceeds of $5,657M exceed the $5,000M gross of the base deal;
  - Boeing said proceeds would be about $5.65B with full exercise.
- The common option was also exercised: $18,200M net proceeds exceed the base gross of $16,087.5M, so 129,375,000 common shares were sold.
- **New figures:**
  - 115,000,000 depositary shares × 0.2914–0.3497 = **33.5M–40.2M common shares**;
  - that is **4.24%–5.09%** of the 790,370,020 cover shares (2026-07-21).
  - This replaces 29.1M–35.0M and 3.7–4.4% in the BA example, case 25 and S3.8.
- Common offering size: 129.4M shares, not 112.5M.

**5. INFQ frame pair (needs owner data).**
- Infleqtion's IR copy of the Q2 2026 10-Q shows only interim figures: 219,743,810 / 15,586,999 for the quarter and 169,199,551 / 15,164,809 for six months.
- The fetch truncated inside a "Correction of Immaterial Errors" table in Note 1. That table is a candidate home for the 46,186,000 / 39,808,027 pair.
- The 10-Q was filed late (12b-25), after updated results.
- Not resolved. The design guard ("check the company's own quarterly series before banding") stands either way.
- Probe: P3.

**6. Review volumes (partly closed).**
- **INTC's FY2025 10-K.** The two "downgrade" sentences sit in MD&A, "Short-Term Investing and Borrowing":
  - an **actual** action: August 2025, corporate rating cut from BBB+ to BBB, agency not named in the filing (the press says Fitch);
  - a consequence sentence about borrowing costs, not a separate action.
  - So the `m04_rating` baseline is exactly 1, and the classifier must not require an agency name.
  - Source: https://www.intc.com/filings-reports/all-sec-filings/content/0000050863-26-000011/intc-20251227.htm
- **MSTR instruments.** Six convertible series at 2026-03-31: 2028, 2029, 2030A, 2030B, 2031 and 2032, about $8.21B.
  - In May 2026, $1.5B of the 2029 notes was repurchased, leaving about $6.71B. The series count is still 6.
  - STRK (Strike preferred) is convertible into Class A.
  - ATM programs: MSTR common (plus a new $21.0B "MSTR Increase" announced 2026-03-23), STRK, STRF, STRD and STRC.
  - Secondary only: search summaries of the 10-Q and Strategy releases; strategy.com returned 403.
- **Pack effect.** The `m04_overhang` baseline is not "about 4 companies, one item per instrument". MSTR alone has about 7 instruments (6 notes + STRK). The total is about 10 with INFQ warrants, the INTC contingent warrant and escrow, and the BA mandatory. A 5-a-week cap therefore flushes over about 2–3 weeks with the other kinds.
- Probe: P4.

**7. Up-C (partly closed).**
- Mayer Brown's "Up-C IPOs and Tax Receivable Agreements" (2025-04-01), slide 12, lists real Up-C IPOs. Large-float candidates still likely to have units outstanding:
  - Ryan Specialty (2021);
  - Dutch Bros (2021);
  - Fluence Energy (2021);
  - Core & Main (2021).
- Nextracker's structure collapsed with Flex's 2024 exit (not verified here).
- Source (law firm, secondary): https://mayerbrown.com/-/media/files/perspectives-events/events/2025/04/up-c-ipos-slides.pdf
- None is on the watchlist. Whether any has a non-dimensional NCI-percentage or unit-count fact is unchecked.
- Probe: P5.

**8. Blank checks (partly closed).**
- **Request-cheap path exists in the repo.**
  - EFTS hits carry SIC codes: `src/engine/sec/fulltext.py`, the `sics` field, stored in `fulltext_hit.sics`.
  - M02 already drops SIC 6770: `src/engine/themes/industries.py` `BLANK_CHECK = "6770"`, used in `candidates.py` and `seasonal.py`.
  - One phrase every SPAC 10-K carries, searched over the 10-K season, lists the year's 6770 filers in a few 100-hit pages.
  - `docs/M00_SEC_DATA.md` line 105 also names the bulk submissions file.
- **Pack effect.** S3.2 can exclude blank checks by EFTS-derived SIC for the whole frame universe, instead of "entity.sic where known, name pattern otherwise".
- **Why so few match by name.** This remains an inference. SPACs report two-class EPS by share class, probably tagged with a class dimension that frames omit. Churchill Capital X (INFQ's predecessor) did tag a non-dimensional 9,000,000, so it is not universal.
- Caution: "the float filter removes them anyway" held for CY2025's 9 names only. A SPAC whose IPO predates its float date reports roughly its trust value, often above $75M.
- Probe: P6.

**9. AMZN/GOOG 424Bs (partly closed).**
- Law-firm and press sources show a steady run of Alphabet debt deals:
  - USD and EUR in Nov 2025 ($17.5B + €6.5B);
  - $20B USD plus GBP in Feb 2026;
  - €9B EUR and CAD, plus a JPY offering, in May 2026;
  - $25B USD in Aug 2026;
  - A$5.5B AUD in Aug 2026.
- That is enough deals for 28 424Bs at about 2 per deal. No Alphabet equity offering was found.
- Amazon: a $15B USD deal in Nov 2025; $37B USD plus €14.5B in Mar 2026.
- Sources: clearygottlieb.com deal notes (Feb 2026, $25B, A$5.5B); seekingalpha.com and datacenterdynamics.com (Amazon). All secondary.
- Filing-by-filing confirmation is what S3.5's fee-exhibit fetch does anyway. Probe: P7.

**10. S-new-68 (not a gap any more).** New sources (pack line 3803) already re-points S-new-68 to Intel's own three 8-Ks, the same accessions as S-new-r3-6. Round 6's citation is therefore primary. At merge, fold S-new-r3-6 into S-new-68 (or the reverse) so that one ID remains. Owner: the merge/renumbering step.

**11. Pack-level critique slices (stays open).** Points 6, 15, 16, 17, 19 and 36 belong to the consolidation drafters (workflow step 4). Round 3 inputs for them from this check:
- the BA range of 4.24–5.09%;
- the Intel escrow cause label and the 71M contingent shares;
- the lock-up stored as a schedule;
- the `m04_overhang` baseline of about 10;
- the `m04_rating` baseline of 1;
- the EFTS-SIC blank-check exclusion.

## Combined probe (owner runs once)
No existing script covers these. They fit one new `scripts/probe_m04_r3.py` modelled on `probe_financing.py` (local part first, then SEC requests, log to `logs/`).

| ID | Local (no requests) | SEC requests |
|---|---|---|
| P1 | — | Archives: SPCX 424B4 of 2026-06-12, primary document (1 request, over 10 MB). Log the "Lock-Up Agreements" and "Shares Eligible for Future Sale" sections. |
| P2 | Stored SPCX Q2 2026 10-Q: log equity-statement rows and sentences with "conversion of" / "convertible preferred" / "6,728". | Optional companyconcept SPCX `StockIssuedDuringPeriodSharesConversionOfConvertibleSecurities`, `ConversionOfStockSharesIssued1` (2). |
| P3 | Stored INFQ Q2 2026 10-Q: find "46,186" and "39,808"; log the table and heading. | If not found: companyconcept INFQ `WeightedAverageNumberOfSharesOutstandingBasic` (1; log accn/form/fp/frame of the CY2025 and CY2024 rows). |
| P4 | Stored MSTR Q2 2026 10-Q: log the convertible-notes table rows and the "Capital Markets Activity"/ATM table (program, size, remaining). | — |
| P5 | — | EFTS "exchangeable for shares of Class A common stock", forms 10-K, 2026-01-01..2026-04-30 (1–3 pages); companyconcept `MinorityInterestOwnershipPercentageByNoncontrollingOwners` for RYAN, BROS, FLNC (3). |
| P6 | — | EFTS "blank check company", forms 10-K, 2026-01-01..2026-04-30, all pages (about 5–10); intersect SIC-6770 CIKs with the stored CY2025 frame file. |
| P7 | List GOOG and AMZN 424Bs since 2023-10-12 from `filing`. | Per 424B: filing index + fee exhibit (2 each; GOOG 28 → 56, AMZN about 10–20). Log the security type. |

Total about 75–95 requests, under a minute at 5/s. P2–P4 need no requests.
