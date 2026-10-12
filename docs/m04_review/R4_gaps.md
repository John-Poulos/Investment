# Round 4 — Known gaps check (survival gate and distress language)

Read 2026-10-12. Scope: the 7 "Round 4" bullets in `docs/M04_DESIGN_PACK.md` Known gaps (lines 3522–3528) and the two "New sources" bullets on Altman Z″ zones and Ohlson (1980) (lines 3559–3560). No SEC host was requested. Non-SEC hosts used: Hofstra (Altman's 2017 slides), FRED, Boeing's newsroom (boeing.mediaroom.com), an S&P Global Ratings criteria copy hosted by S&P Maalot, StockTitan (filing summaries) and web-search relays of filing text. Repo files read: `reference/old_engine/financial_intelligence.py`, `src/engine/themes/proposals.py`, `src/engine/sec/events.py`, `scripts/`.

## Summary
| # | Gap | Status | Changes pack? |
|---|---|---|---|
| 1 | 4.4 class sentences not read verbatim | needs live probe | no (one wording check) |
| 2 | INFQ "substantial doubt" hit, class unknown | needs owner data | **yes** (S4.5 SPAC rule) |
| 3 | Boeing covenant-compliance sentence | partly closed | no |
| 4 | Manufacturer Z needs Tiingo prices | needs owner data | no |
| 5 | Pack-wide points 6, 15, 16, 17 | stays open (consolidation step) | no |
| 6 | Point 36 mock-up; point 19 stage order | partly closed | no |
| 7 | 8-quarter warn, capex-funded tier, weekly cap 5 unsourced | partly closed | **yes** (labels; two S4.2 refinements) |
| 8 | Altman Z″ zones 1.10 / 2.60 primary | closed | no |
| 9 | Ohlson (1980) primary | partly closed | no |
| 10 | New: 8-K Item 3.01 also covers voluntary listing transfers | partly closed | **yes** (S4.1 trigger) |
| 11 | New: Boeing undrawn revolvers are stated in its releases | closed | **yes** (Boeing worked example, 4.3 argument) |

## Findings

**1. Class example sentences (needs live probe).**
- Nothing new can be read without www.sec.gov. Full sentences and offsets must be captured as fixtures anyway (D-SRCH-19).
- Albemarle check (web-search relay of the amendment text, secondary): relief period, 5.75× peak leverage at Q2 2025 and 1.00× minimum interest cover match the pack. The relay describes *limits* on buybacks and dividends. The pack says "buybacks barred". Check that word at capture.
- Probe P1.

**2. INFQ hit (needs owner data) — and a rule fix.**
- The class is still unknown. Two secondary summaries of INFQ's 8-K 4.01 (2026-03-26) disagree on whether Withum's SPAC reports carried going-concern doubt. Not guessed.
- **Timing fact** (StockTitan, secondary): the de-SPAC completion 8-K is dated 2026-02-17. The 4.01 says Withum leaves after finishing the 2025 audit (event 2026-03-20). So the FY2025 10-K with the SPAC's statements was filed **after** the close.
- **Pack effect.** S4.5 labels hits `spac_pre_merger` only "in filings dated before a de-SPAC close". INFQ's hit would escape that rule. Key it on the statements' period end (period of report ≤ the 2.01 close date), not the filing date.
- Probe P2 (local first).

**3. Boeing covenant sentence (partly closed).**
- A web-search relay of Boeing's Q2 2022 10-Q (secondary) gives the compliant-class sentence: "we were in compliance with the covenants for our debt and credit facilities."
- The FY2023 10-K and 2024 10-Q matches are still unread in context. UTI can stay the compliant example; Boeing is a second one once captured.
- Probe P1 (one extra document).

**4. Manufacturer Z (needs owner data).**
- Market value needs stored Tiingo closes and dei share counts; Claude may not read `data\`.
- Two notes that need no data:
  - GFS is probably SIC 3674, a manufacturer. Under S4.4 it gets manufacturer Z, not Z″, so the book Z″ of 1.87 is not the score the design would use.
  - 1.87 is grey, not distress, so it would not raise `m04_score_gap` either way.
- Probe P3 (0 SEC requests).

**5. Pack-wide points 6, 15, 16, 17 (stays open).** Owned by the consolidation step (user step 4: drafting agents, then the critic). Round 4's rows are S4.8, S4.11 and S4.12.

**6. Points 36 and 19 (partly closed).**
- Point 19 is resolved by ordering. Round 5's header says question 5.1 (stage) is "presented with Round 1", and the owner's plan presents Round 1 first. So `lifecycle_stage` is decided before Round 4.
- Point 36 stays open as a build step: the gate-panel mock-up comes before the build (D-UI-4).

**7. Unsourced thresholds (partly closed: a published anchor exists).**
- **Source.** S&P Global Ratings, "Methodology And Assumptions: Liquidity Descriptors For Global Corporate Issuers" (2014, republished 2016), plus the 2019 guidance:
  - *Strong* liquidity looks over 24 months: sources ÷ uses of at least 1.5× for the next 12 months, and above 1.0× for the following 12.
  - *Adequate* looks over 12 months: at least 1.2×.
  - Undrawn committed credit counts only if the facility matures beyond the horizon. Availability blocked by covenants is excluded.
  - Capex: the 12-month adequate test counts maintenance, contracted and committed long-lead projects. Growth capex that can be curtailed is left out. The 24-month strong test counts all capex, discretionary growth included.
- **Mapping (our arithmetic; constant burn, no maturities, so 12-month sources ÷ uses = runway ÷ 4):**
  - fail below 6 quarters = below 1.5× in year 1;
  - warn below 8 = not above 1.0× in year 2;
  - S&P's adequate floor (1.2×) = 4.8 quarters.
  - So the pack's 6 / 8 pair matches S&P's "strong" test exactly. It is stricter than "adequate".
  - Caveat: S&P works on stressed forecasts plus qualitative factors. Our runway is trailing only. The 6 / 8 pair becomes a sourced analogy, not a calibrated value.
- **Capex-funded tier.** S&P's split supports it: total-capex burn is tested only at the 24-month level.
- **Refinements for the owner (S4.2):**
  - (i) Count undrawn credit only when it matures beyond the test horizon: 12 months for the fail and for 4.3a, 24 months for the warn. Exclude availability blocked by covenants.
  - (ii) Once A2 maintenance capex exists, the fail test could use OCF − maintenance capex (the S&P 12-month analogue). Total capex would keep the 8-quarter warn.
- **Weekly cap of 5:** no published source. Repo precedent: M02's cap is 10 judgment items a week, counted per `module_id` (`proposals.py`, `WEEKLY_CAP = 10`, D-M02-51). M04's 5 would add to it, up to 15 judgment items a week. It stays a starting value.

**8. Altman Z″ zones (closed).**
- Altman's own 2017 slides were downloaded and read today:
  - slide 27 gives Z″ = 3.25 + 6.56X1 + 3.26X2 + 6.72X3 + 1.05X4, with safe above 5.85, grey from 4.35 to 5.85 and distress below 4.35;
  - slide 28 gives the 2013 medians: B 4.03, CCC 2.57, and 0.05 for 94 Chapter 11 filers.
- 1.10 / 2.60 equal 4.35 / 5.85 minus the 3.25 constant. No Altman text states 1.10 / 2.60 for the form without the constant. The 2018 MDPI paper returned 403.
- The Round 4 text already uses this. The Known-gaps bullet is stale.

**9. Ohlson (1980) (partly closed).**
- Round 4's body says the original was read through an Internet Archive copy (S-new-r4-2), so the "not read" bullet is stale.
- Today's re-fetch failed: HTTP 429, and WebFetch is blocked for web.archive.org. The page-level facts (0.038 cut-off, 17.4% / 12.4% errors) were not re-read.
- Re-verified today:
  - Model 1 with the published coefficients reproduces Rivian O = −3.44, P = 0.031. Assets in $ millions give P = 0.90. The shifts are 5.62 and 1.87.
  - FRED GNPDEF: the 1968 quarters average 18.243. Rebased to 1968 = 100, the annual averages are 577.1 (2020), 603.3 (2021) and 706.0 (2025), as in the pack.

**10. New — Item 3.01 is not always distress (partly closed).**
- Item 3.01's heading includes "Transfer of Listing". Voluntary exchange moves are filed under it: Dillard's (NYSE to the Texas Stock Exchange, 2026), Oasis (2019) and Baker Hughes (2021), all seen as search-result headings.
- StockTitan lists INFQ's 2026-02-03 8-K as an "NYSE listing move" (secondary). That is the 3.01 the pack lists.
- The engine catalog (`sec/events.py`) titles 3.01 without the transfer clause and types it red_flag/high.
- **Pack effect.** S4.1 and S4.12 fail the gate on any 3.01. Fail only on a deficiency notice or a delisting decision. A transfer becomes a note. This needs a text class or a review item. It also answers part of the Round 1 gap on INFQ's 3.01.
- Probe P2 reads the INFQ 8-K.

**11. New — Boeing's revolvers (closed; changes the worked example).**
- Boeing's own releases state undrawn credit:
  - $14.7B at Q2 2022 (2022-07-27 release);
  - $10.0B at Q2 2024 (2024-07-31 release).
- A relay of 2020 10-Q text gives $9.6B at 2019-12-31 (secondary).
- The relayed Q2 2022 10-Q sentence gives the 2022 maturities: $6.3B in October 2022 ($3.1B with a term-out option), $5.3B in March 2023 and $3.2B in October 2024.
- Re-run with S4.2's own text finder confirmed ($M):

| Date | Cash-only runway / 4.3a | With stated credit | Credit maturing beyond 12 months only |
|---|---|---|---|
| FY2019 | 3.6 fail / fail | 7.1 warn; 18,452 vs 19,630 pass | split not read |
| Q2 2022 | 6.1 warn / fail | 14.0 pass; 12,902 vs 26,148 pass | 7.8–9.5 warn or pass; 4.3a pass |
| Q2 2024 | 3.1 fail / fail | 5.5 fail; 21,277 vs 22,621 pass | depends on the split ($0.8B expired August 2024) |

- **Pack effect.**
  - "Q2 2022 is the only point where 4.3a changes the verdict" holds only on cash-only liquidity.
  - Once the credit line is confirmed, 4.3a changes no Boeing verdict, and FY2019 becomes a warning, not a fail.
  - The 4.3a vs 4.3b argument should show both columns. The S4.9 Boeing regression cases need a with-credit variant.
  - Refinement (i) under gap 7 decides the third column.

## Probes (one combined owner run)
| ID | What | Endpoint | Requests | Script |
|---|---|---|---|---|
| P1 | Text fixtures: the 8 S4.10 documents (Fisker FY2023 10-K, Invitae Q2/Q3 2023 10-Qs, Proterra FY2022 10-K, Microvast FY2025 10-K, Riot FY2025 10-K, UTI Q3 FY2025 10-Q, Albemarle EX-10.1) plus Boeing's FY2023 10-K for the covenant sentence | Archives documents | 9 | none yet. Planned `scripts/run_survival.py --fixtures` (S4.10). For now, a small probe on the `probe_financing.py` pattern using `engine.sec.documents` |
| P2 | INFQ: class of the "substantial doubt" sentence in its FY2025 10-K; cause of the 8-K 3.01 of 2026-02-03 | Local first: FTS5 on `corpus.db`, where the latest 10-K should already be stored (DS7). Else Archives (0001193125-26-134544) plus the 3.01 8-K | 0–2 | none. Local SQL, or the P1 probe |
| P3 | Manufacturer Z for SIC 2000–3999 watchlist names: latest balance-sheet date, close on that date (Tiingo, stored), dei shares outstanding (all classes) and the five ratios from `fact` | Local `engine.db` only | 0 | none. A local-only step in the same probe (`probe_seasonal.py` has a `--no-sec` precedent) |
| P4 (optional) | Boeing revolver maturity split at 2019-12-31 and 2024-06-30 (refinement i) | Archives: FY2019 10-K, Q2 2024 10-Q | 2 | P1 probe |

Total: about 11 SEC requests, under a minute.

## Sources (read 2026-10-12)
- Altman (2017) slides 27–28 — https://www.hofstra.edu/pdf/community/bdc/breslin/breslin-evolution-of-altman-z-score.pdf (primary, author's own)
- Altman (2018), IJFS 6(3):70 — https://www.mdpi.com/2227-7072/6/3/70 (403, not read)
- FRED GNPDEF — https://fred.stlouisfed.org/data/GNPDEF.txt
- S&P Global Ratings, Liquidity Descriptors criteria (2014, republished 2016) — https://maalot.co.il/Publications/MT20170309124234.pdf ; guidance (2019-12-04) — https://www.maalot.co.il/Publications/CG20191219113143.PDF (primary, rating-agency criteria)
- Boeing Q2 2022 release — https://boeing.mediaroom.com/2022-07-27-Boeing-Reports-Second-Quarter-Results ; Q2 2024 release — https://boeing.mediaroom.com/2024-07-31-Boeing-Reports-Second-Quarter-Results (primary, company)
- StockTitan INFQ/CCCX 8-K list and 4.01 summary — https://stocktitan.net/sec-filings/CCCX/8-k.html (secondary)
- Repo: `reference/old_engine/financial_intelligence.py:75-76` (12 / 24-month ladder); `src/engine/themes/proposals.py:30, 98-104` (per-module weekly cap); `src/engine/sec/events.py:86-91` (3.01 catalog entry)
