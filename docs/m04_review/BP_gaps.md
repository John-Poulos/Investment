# M04 review — Build parts: Known gaps check

Checked 2026-10-12 against `docs/M04_DESIGN_PACK.md` lines 3145–3484 (Build parts) and 3485–3565 (Known gaps). No SEC, Tiingo, `.env` or `data\` access. Covers the eight "Build parts (proposal)" gaps and two "New sources" bookkeeping gaps.

## Summary

| # | Gap (pack line) | Status | Changes the pack? |
|---|---|---|---|
| 1 | Live-check minutes are estimates; bandwidth not measured (3551) | partly closed | no |
| 2 | Peer counts for Part 2 and Part 8 are estimates (3552) | needs owner data | no |
| 3 | Tiingo coverage of delisted episodes (3553) | needs live probe | no |
| 4 | dei error-correction flag on 10-Ks filed in early 2023 (3554) | partly closed | **yes**: Part 3's 36 R1 pages fall to about 24 |
| 5 | Review volumes are estimates (3555) | partly closed | **yes**: the review-kinds table is out of step with Rounds 2, 4 and 5 |
| 6 | Label of GE's `UnbilledContractsReceivable` line (3556) | **closed** | no (adds a sub-total note for Round 2) |
| 7 | Sizes of instances, the 44 walk filings and the 143 EFTS documents (3557) | partly closed; rest needs owner data | no |
| 8 | engine.db size and growth (3558) | needs owner data | no |
| 9 | Citation fixes in other rounds (3563) | partly closed: 7 of 10 already applied | **yes**: 3 fixes still to apply |
| 10 | S-new-src ID collisions (3564) | not a gap any more | no (but 17 sources sit under 2–5 IDs each) |

Gaps 1, 4, 7 and 8 are settled by one **local, read-only** query the owner runs: no SEC or Tiingo request (probe A below). Gap 3 needs about 6–12 Tiingo requests (probe B).

## Findings

**1. Live-check minutes (partly closed).**
- The budget arithmetic checks out. Per-part requests add up to 1,132–1,189: Part 1 = 164 + 17, Part 2 = 130–140, Part 3 = 88, Part 4 = 215, Part 5 = 220, Part 6 = 16, Part 7 = 249, Part 8 = 50–80. That matches "about 1,130–1,190".
- Pacing alone is about 4.5 minutes for all eight parts (1,190 ÷ 265 a minute).
- Instance reads are already measured. M02 read 113 instances in about one minute: the log header shows 22:18 UTC and the file was written at 18:19:12 local time (`logs/money_20261009-181912.txt`). So Part 7's ~160 instances take about 1.4 minutes, whatever the file sizes.
- A repo fact the pack leaves out: the SEC client sends `Accept-Encoding: gzip, deflate` (`src/engine/sec/client.py:250`). The MB figures (45 MB, 150–185 MB, 185–300 MB) are decompressed JSON sizes, so the minutes estimated from them are an upper bound. The compression ratio was not measured (the stored fixtures are too small to test).
- Still open: the owner's bandwidth. Neither `fetch_log` nor `http_cache` records wire bytes or response times (`src/engine/store/http.py`). Recommendation: keep the pack's guard (each part log prints requests, MB and seconds per fetch type). No separate probe is needed.

**2. Peer counts (needs owner data).**
- No peers are stored. `peer_group` and `peer_member` exist (migration 0001) but nothing writes them, and `config/watchlist.toml` has no peer entries.
- The counts depend on the owner's Part 2 confirmations and Part 8 episode choices. The pack's MB ranges follow from them: 40–50 × 3.7 MB = 148–185 MB, and 50–80 × 3.7 MB = 185–296 MB.
- No probe now. Part 2's browse-by-SIC pages give the candidate counts.

**3. Tiingo coverage of delisted episodes (needs live probe).**
- Nothing can be checked without the owner's key. Tiingo's symbology page (S-new-bp-1) says delisted data is kept only for tickers that have not been recycled, and that delisted symbols may end in a digit. So recycling cannot be guessed from the ticker alone.
- **Do not use `scripts/run_prices.py --symbols` for this.** It fetches and stores price bars keyed by ticker (`src/engine/prices/tiingo.py`, `daily()` only), so a recycled ticker would store another company's bars. `tiingo.py` has no metadata call. See probe B.
- This gap duplicates Round 1 (3492) and Round 6 (3540). One probe closes all three.

**4. dei error-correction flag on early-2023 10-Ks (partly closed; changes Part 3's count).**
- The 10-K cover-page clawback checkboxes took effect on 2023-01-27. Staff guidance the same day (C&DI 121H.01) said compliance was not expected until issuers must have a recovery policy. Listing standards had until 2023-11-28 to take effect, plus 60 days to adopt a policy. Source: TheCorporateCounsel.net, 2023-01-30 (secondary; legal commentary): https://www.thecorporatecounsel.net/blog/2023/01/new-form-10-k-checkboxes-some-urgent-staff-guidance.html (read 2026-10-12). The pack's own C&DI 104.20 reading (S-new-src-3) covers only the 2025 guidance.
- Practice varied in 2023: some 10-Ks filed after 2023-01-27 included the boxes and some left them out (summary of compensationstandards.com and PLI SEC blog posts found by search; secondary).
- EDGAR Release 23.1 added the 2023 DEI taxonomy on 2023-03-20 (XBRL US news, https://xbrl.us/news/sec-edgar-upgrade-23-1, read 2026-10-12). The source does not say which DEI version first defined `DocumentFinStmtErrorCorrectionFlag`, and the SEC release notes sit on xbrl.sec.gov, which is off-limits. So that point is unverified.
- **Consequence.** A watchlist 10-K filed before December 2023 was not required to carry the flag. Apple's 10-K for the year ending in late September is normally the year's last, filed in early November, so all 12 watchlist 10-Ks filed in 2023 likely fall before that date. This is an inference: the filing dates are in engine.db and were not read; probe A lists them.
  - A missing flag on those filings means "not required yet". It is never "false".
  - Part 3 needs R1 pages only for 10-Ks filed from 2023-12-01: about 24 of the 48, less the 12 already read in Part 1. The pack's 36 is an upper bound and is probably nearer 24 (in practice 12–24, depending on how many of Part 1's 12 are post-2023 10-Ks).
  - The checkboxes apply to annual reports only, not to 10-Qs (secondary summaries; this matches the C&DI scope the pack quotes).

**5. Review volumes (partly closed; the table needs merging).**
Comparing the Build parts table (3369–3378) with each round's own review tables finds three problems:
- **`m04_restate`:** the Build parts table says about 6 a year (101 steps ÷ 16 years). Round 2 (line 983) says at most 4 at first run, then about 2–3 a year, because most steps are labelled automatically. Use Round 2's figure.
- **Kinds missing from the Build parts table:**
  - `m04_gc_text`: under 1 a quarter (Round 4, line 1792);
  - `m04_covenant`: under 1 a month (line 1793);
  - `m04_score_gap`: 0–1 at first run (line 1794);
  - `m04_customer`: 1–3 a quarter, unmeasured (Round 5, line 2451);
  - `m04_unit_kpi`: about 1 a year (line 2452);
  - `m04_mscore` as a separate kind: 1 now (Round 2, line 985).
- **Caps and priority conflict.** Round 5 sets per-kind caps (5, 3 and 2 a week), and Rounds 2, 4 and 5 each number their priorities from 1. B.3a proposes one M04 cap of 5 a week and one global order (1–7). The round answers should settle which rule wins.
- **Merged steady-state estimate:** about 25–55 items a year, or 0.5–1.1 a week. Of that, survival kinds are about 3–16, events 2, restate 2–3, dilution 4–8, margin 1–4, estimate and M-score 2–3, stage 4–5, CvD about 2, customer 4–12 and unit KPI 1. B.3a's "under one a week" holds only at the low end. The cap of 5 still absorbs the high end.
- Still open: every volume except events, walk steps and EFTS hits remains an estimate until the first part logs.

**6. GE `UnbilledContractsReceivable` label (closed).**
- GE's 2017 annual report on GE's own domain was read on 2026-10-12: https://www.geaerospace.com/sites/default/files/GE_AR17.pdf (its pages carry "GE 2017 Form 10-K" footers).
- The Statement of Financial Position line is **"Contract assets (Note 9)"**: 28,861 at 2017-12-31 and 25,162 at 2016-12-31. Both match the tag values in the pack's fixture row.
- Note 9, "Contract assets", gives the components:

| $M | 2017 | 2016 |
|---|---|---|
| Long-term product service agreements | 15,157 | 12,752 |
| Long-term equipment contract revenue | 6,954 | 5,859 |
| **Revenue in excess of billings** | **22,111** | **18,611** |
| Deferred inventory costs | 3,839 | 3,349 |
| Nonrecurring engineering costs | 1,814 | 2,185 |
| Customer advances and other | 1,097 | 1,018 |
| **Contract assets** | **28,861** | **25,162** (components add to 25,163; rounding) |

- The product-service balances are shown net of billings in excess of revenues: $3,037M at 2017 and $3,750M at 2016 (Note 9, footnote b). These may be the `BillingsInExcessOfCost` values; confirm when Part 6 captures that tag.
- The MD&A says contract assets rose $3.7B. Revenue in excess of billings rose $2.4B on service agreements and $1.1B on equipment.
- **Note for Round 2:** about 23% of the line is not unbilled revenue (deferred inventory, engineering costs, advances). On the revenue-in-excess-of-billings subtotal the 2017 rise is +18.8%; on the total line it is +14.7%. The fixture value stays as it is. Round 2's contract-asset gap may prefer the subtotal when a note gives it.
- This also closes the Round 1 duplicate (3496).

**7. Sizes of instances, walk filings and EFTS documents (partly closed).**
- Instances are not cached (`moneyflow/instance.py:152`, `ttl_s=0`), so their sizes cannot be read locally. Their read rate is already measured (gap 1).
- The 44 walk filings and the 143 EFTS hits are 10-K/10-Q documents. Their size is approximated by the 10-K/10-Q documents already in `corpus.db`'s `http_cache`, fetched with `DOC_TTL_S` (`src/engine/sec/documents.py:361`). Probe A measures them locally. Older filings (2001–2015) are usually smaller, so the sizes are an upper bound.

**8. engine.db size and growth (needs owner data).**
- Probe A prints the file sizes and fact rows per CIK, which give bytes per company. Growth per added peer ≈ engine.db MB ÷ total fact rows × that peer's fact rows.

**9. Citation fixes in other rounds (partly closed).**
The current pack text was checked with grep:
- **Already applied (7):**
  - fix 1 and fix 2: S98 no longer appears in any round;
  - fix 3: edgar.tools is gone from Round 1;
  - fix 6: Round 3's Commerce row at line 1181 has the two tranches and the blended $20.47, and line 1182 has the contingent warrant;
  - fix 7: no "URL to add" left;
  - fix 8a: Round 6 says the 29,619 base "is now verified", and no asterisk remains;
  - fixes 9 and 10: Round 1 and Round 2 cite the same sources under S-new-r1-3/r1-4 and S-new-r2-3.
- **Still to apply (3):**
  - **Fix 4:** Round 2 line 736 still says net income +$3.0B and the prior 4-year life are "still to re-confirm in Note 1". S-new-22 confirms both from R10. The Round 2 gap at line 3501 is stale for the same reason.
  - **Fix 5:** Round 2 line 674 quotes the RFS figure (65% of 452), while Round 3 line 1064 quotes the working paper (64% of 447). Name the version, or use the RFS figure in both.
  - **Fix 8b:** Round 6 lines 2679 and 3047 show inventory days of 153/235 without the primary-computed 151/213 beside them.
- **Owner of the work:** the Round 2, 3 and 6 brief writers in this review, or SB.1's docs-only step on the review branch.

**10. S-new-src ID collisions (not a gap any more).**
- Checked with grep. Each section uses its own prefix: S-new-n (69), S-new-r1…r6, S-new-bp, S-new-src. All 131 provisional IDs are defined exactly once, and every cited ID is defined. So S-new-src cannot collide.
- **The real merge issue is duplicates, not collisions.** 17 URLs are defined under 2–5 IDs each. Examples:
  - companyfacts: S-new-1, r1-1, r2-8, r4-4, r6-1;
  - Form 8-K PDF: r1-2, r2-1, r3-3, src-1;
  - Rule 12b-25: r1-4, r6-4, src-5;
  - Intel 8-Ks: S-new-68 and r3-6;
  - Lee (2012): r2-3 and src-6.
- **Mapping is incomplete.** The pack's note (line 3567) maps only S-new-n to S123 onward. SB.1 must map all 131 provisional IDs, merging the duplicates, to S122 onward. S122 is reserved for McConnell & Muscarella.
- S-new-bp-6 (browse-by-SIC) is defined but cited nowhere; the Part 2 row should cite it.

## Probes for the owner's combined run

**A. Local, read-only (0 SEC, 0 Tiingo requests), for gaps 1, 4, 7 and 8.** Run from the repo root in PowerShell:

```powershell
@'
import os, sqlite3, statistics as st
E = sqlite3.connect("file:data/engine.db?mode=ro", uri=True)
C = sqlite3.connect("file:data/corpus.db?mode=ro", uri=True)
for f in ("data/engine.db", "data/corpus.db"):
    print(f, round(os.path.getsize(f) / 1e6, 1), "MB")
print("fact rows", E.execute("SELECT count(*) FROM fact").fetchone()[0])
for cik, n in E.execute("SELECT cik, count(*) FROM fact GROUP BY cik ORDER BY 2 DESC"):
    print(" ", cik, n)
periodic = {a.replace("-", "") for (a,) in E.execute(
    "SELECT accession FROM filing WHERE form IN ('10-K','10-Q','10-K/A','10-Q/A','20-F')")}
sizes = {"companyfacts": [], "10-K/10-Q files": [], "efts": [], "frames": [], "other": []}
for url, n in C.execute("SELECT url, length(body) FROM http_cache WHERE outcome = 'ok'"):
    k = ("companyfacts" if "companyfacts" in url else "efts" if "efts" in url
         else "frames" if "/frames/" in url
         else "10-K/10-Q files" if any(p in periodic for p in url.split("/")) else "other")
    sizes[k].append(n)
for k, v in sizes.items():
    if v:
        print(k, len(v), "files; median", round(st.median(v) / 1e6, 2), "MB; max",
              round(max(v) / 1e6, 2), "MB; total", round(sum(v) / 1e6, 1), "MB")
print("10-Ks filed in 2023 (dei flag not required before about 2023-12-01):")
for row in E.execute("SELECT cik, form, filed FROM filing WHERE form = '10-K' "
                     "AND filed BETWEEN '2023-01-01' AND '2023-12-31' ORDER BY filed"):
    print(" ", *row)
'@ | uv run python - > logs\m04_local_probe.txt 2>&1
```

**B. Tiingo metadata (gap 3, also Round 1 and Round 6): about 6–12 requests and no price storage.**
- Call `GET https://api.tiingo.com/tiingo/daily/<SYMBOL>` (metadata: name, exchangeCode, startDate, endDate). Send the key in the header, as `tiingo.py` does.
- Symbols: NVTA (Invitae), RAD (Rite Aid), JCP (J.C. Penney), SHLD (Sears Holdings), FIT (Fitbit), BBBY. For BBBY, expect the renamed Beyond, Inc.; check that startDate and name do not reach back to the old Bed Bath & Beyond.
- Add any digit-suffixed or Q-suffixed variants that a 404 points to.
- The pass test: the returned name and date range match the SEC company over the episode window.
- No existing script does this without storing bars. Add a `probe` path to Part 8's `run_financials.py cvd`, or a small `probe_tiingo.py`; either needs to be written. It fits the batch budget (40 an hour) and uses 6–12 of the month's symbols.
- An optional zero-request alternative is Tiingo's supported-tickers file (ticker, exchange, startDate, endDate). Its download URL and whether it needs a key were not verified here.

## Sources read (2026-10-12)
- Repo:
  - `docs/M04_DESIGN_PACK.md`
  - `src/engine/sec/client.py`
  - `src/engine/store/http.py`
  - `src/engine/sec/documents.py`
  - `src/engine/moneyflow/instance.py`
  - `src/engine/prices/tiingo.py`
  - `scripts/check_tickers.py`, `scripts/run_prices.py`, `scripts/fetch_stats.py`
  - `src/engine/store/migrations/engine/0001_initial.sql`, `src/engine/store/migrations/corpus/0002_not_found.sql`
  - `logs/money_20261009-181912.txt`, `logs/fetch_stats_20261007-220253.txt`
  - `docs/SOURCES.md`
- GE 2017 Annual Report (primary, company-hosted): https://www.geaerospace.com/sites/default/files/GE_AR17.pdf
- TheCorporateCounsel.net, 2023-01-30 (secondary): https://www.thecorporatecounsel.net/blog/2023/01/new-form-10-k-checkboxes-some-urgent-staff-guidance.html
- XBRL US, EDGAR 23.1 (secondary): https://xbrl.us/news/sec-edgar-upgrade-23-1
