# Data sources & gaps register

Updated: 2026-10-08 · One place for data the engine needs but does not have yet (or has but does not parse). Each module build checks this list; an entry closes with the decision that covers it. Free sources only for now (S2). Evidence grades per D14.

## Status key
- **gap** — not collected.
- **stored, not parsed** — kept whole in corpus.db and searchable (Tier 2); no extractor yet.
- **partial** — some forms covered; the rest named in Notes.
- **covered** — closed by the decision named.

## Register
| ID | Need | Source (free) | Grade | Status | Modules | Notes |
|---|---|---|---|---|---|---|
| DS1 | Guidance given on the earnings call, not in the release (Microsoft, Apple; Alphabet beyond capex; Boeing) | Company IR sites: call webcast pages, prepared remarks and slides (e.g. Micron posts prepared remarks and slides at investors.micron.com; intc.com/financial-info/financial-results lists, per quarter, the earnings release, earnings deck PDF and prepared-remarks PDF — checked 2026-10-08) | A | gap | M11 (R19), M02, M04 | Seen 2026-10-08: release outcome `none` for MSFT, AAPL, most GOOGL, BA. Starting point: owner's `ir_feeds.py` (D-M02-2). To decide at build: which IR documents each company publishes, and how they are stored (company-published documents vs the snippet-only rule for news in D-M02-2). Third-party transcripts are paid or restricted → not planned. |
| DS2 | Operating-metric releases: Tesla quarterly production, deliveries and storage deployments | 8-K EX-99.1 (already fetched nightly) | A | stored, not parsed | M04, M11 (milestones R4), M08 | Kept whole and searchable; the guidance parser correctly reports "no guidance" for them. Needs a KPI extractor (by model line, prior quarter, year ago). Survey other watchlist companies for similar releases at that build. |
| DS3 | Guidance wording the R19 parser does not read (growth rates such as "revenue growth forecasted to exceed 40%", qualitative raises) | Earnings releases (stored) | A | partial | M11 (R19) | Goes to the review queue with the exact sentence (D-SRCH-11/12); extend the parser when patterns repeat. |
| DS4 | Theme news beyond filings | Company IR RSS (phase 1), curated trade-press RSS (phase 2) | A / B | gap | M02 | Per D-M02-2; feeds to pick at the M02 build. |
| DS5 | Options chains and IV history | To find (may need own daily IV snapshots) | — | gap | M12 | Q5 in DESIGN.md. |
| DS6 | Form 4 bulk data sets | SEC insider-transactions data sets | A | gap (deferred) | M07 | Per-filing Form 4s are parsed today (D-SEC-10); bulk sets only if the universe grows. |
