# M02 — Build log (running)

Updated: 2026-10-10 · Companion to M02_THEMES.md (decisions live there; this file holds what each build conversation needs) · Cross-module lessons: LESSONS.md

## How to use
- A build conversation reads M02_THEMES.md, then its part below, then LESSONS.md.
- Each part records: agreed spec (decision IDs), what to reuse, live-test labels, open items, and notes written during the build.
- Lessons that would help another module go to LESSONS.md, not here.

## Design review (2026-10-08 conversation)
One section per proposed amendment, discussed with the owner in order. Outcome lines are filled in as each is settled.

| # | Amendment | Outcome | Decision |
|---|---|---|---|
| 1 | Forward money flow from the guidance ledger | accepted, modified: positive for spender and suppliers; definition tags; stale flag; quoted theme link; call guidance from IR documents | D-M02-5, D-M02-6 |
| 2 | Gemini roles | modified: code mines phrases, Gemini names; phrase tests; code finds links, Gemini labels, owner confirms; use case 5b approved | D-M02-8, D-M02-9, D-SRCH-21 |
| 3 | Digest delivery | accepted, extended: weekly events + seasonal pass; per-item, grouped, cap 10/week; 5 item kinds; crowding flag | D-M02-10 |
| 4 | Tracked tier in the UI | accepted, extended: toml core + DB promoted; promotion suggestions; 12-month still-track review | D-M02-11 |
| 5 | Price budget for the tracked tier | dropped (premise wrong: cap counts unique symbols); revised for logon-only runs: watchlist daily, tracked 3-day rotation, 8 req/h kept for the app | D-M02-12 |
| 6 | News sources | modified: Tiingo News dropped; IR RSS polled; Finnhub + Massive; 11 trade-press feeds; arXiv, USAspending, Federal Register, Congress.gov | D-M02-13 |
| 7 | Search inputs | modified: 5/s pace; form.idx denominator; 10-page cap with lower bound; section + quantified rule; queued drill-down | D-M02-14 |
| 8 | Failure modes | approved: 12 rows + capex-funding row added; ★ guards are build requirements | D-M02-15 |

## Build parts (owner approved order 2026-10-09, revised: part 4 before part 3, D-M02-19; one conversation each, Medium effort)
| Part | Covers | Decisions | Depends on | Live checks (owner runs) | Status |
|---|---|---|---|---|---|
| 1 Theme core | `config/themes.toml` seeds + DB themes/phrases with `discovered_at`; EFTS breadth with `form.idx` denominator, 10-page cap, lower bound; Themes tab v1 (share of filers, same window YoY) | D-M02-1, -14, -16, -17 | M00 | done: probe + first run 2026-10-09 | built (branch `m02-theme-core`) |
| 2 Plumbing | Review kinds m02_theme/phrase/candidate/link/input/ir_download; weekly header, cap 10, suppression; guide panel; tracked tier tables + side panel core/promoted/tracked; promotion suggestion + 12-month review; price rotation (tracked 3-day) + 8/h app reserve; end-of-run summary box | D-M02-10, -11, -12 | 1 | one refresh with a tracked name | built (branch `m02-plumbing`) |
| 3 Money flow | Derived spenders + candidates; latest capex guidance per spender (any grade, forms as stated, calendar rule); six freshness states; own-definition actuals (recipes, override file, stated-actuals reconciliation); capital allocation (all debt tags, coverage check, tag discovery); spender→theme links; supplier RPO; per-spender view | D-M02-5, -15, -19, -20, -28…33 | 1, 2, 4 | `run_money.py` (see part 3 notes) | built (branch `m02-part3`, live checks 1–2), PR opened |
| 4 Call guidance | Alpha Vantage adapter (probe done 2026-10-09: works, fiscal labels); Downloads PDF pickup + m02_ir_download (lean, D-M02-21); call parser + direction rows; release vs call; grade B → A on match; clause tag + "definition changed"; labels | D-M02-6, -20, -21, -22 | 2 | `run_calls.py --import-probe --fetch 6` | built (branch `m02-call-guidance`, live checks 1–4) |
| 5 Suppliers L0–L3 | Reverse lookup with alias table; L1 passages; Exhibit 10 ingest for Item 1.01; Gemini 5/5b; labelled precision set (~30); m02_link/m02_input | D-M02-7, -9, -15, -35, -36 | 1, 2 | NVDA reverse lookup; Gemini labels on the labelled set | merged (PR #21, 2026-10-10) |
| 5b Financing links | Equity purchases, equity granted to customers, revenue backstops, customer financing/guarantees, JVs (K1–K4, K6): text finders over stored filings, 8-K 3.02/1.01 exhibits, 13F + 13D/13G readers, XBRL credit quality (financing receivables, allowances); loop flag; Money flow tab section; digest items; review-guide examples | D-M02-41…45 | 5 | one combined check (13F/13D for NVIDIA, re-read, XBRL probe) | built 2026-10-10 (D-M02-46); live checks 1–3 → D-M02-47, -48; PR opened |
| 6 Seasonal pass | Corpus phrase mining; phrase tests (hits, ≥ N companies, industry spread, samples); Gemini 4 naming; candidate proposals (section + quantified rule); crowding flag; first-mention flags | D-M02-8, -10, -14, -15 | 1, 2, 5 | one seasonal run | — |
| 7 News & feeds | IR RSS; Finnhub + Massive; 11 trade-press feeds; arXiv, USAspending, Federal Register, Congress.gov; dedupe; weekly event digest content | D-M02-13, -15 | 2 | one weekly digest | — |

Effort: High only if a part raises a new design question; otherwise Medium. Each part: branch → fixture tests → owner live check → PR → merge (DESIGN.md workflow).

## Live checks without slowing development (owner request 2026-10-09)
- Test the piece, not the whole run: `run_themes.py --themes <key>`, `run_prices.py --symbols A,B`, `run_live.py <label> <test file>`, `run_refresh.py --skip-prices` (SEC step only, seconds when little was filed).
- One live check per part, at the end of the part, combining everything that part needs into one command where possible; fixture tests cover the rest.
- The full refresh (with prices) only when a part changes the refresh itself; with 3 s spacing it now takes ~1–2 min for ~30 symbols.

## Notes per part
(filled during the review and the builds)

### Part 1 — Theme core (built 2026-10-09, D-M02-17)
- Code: `themes/seeds.py`, `themes/universe.py`, `themes/breadth.py`, `themes/views.py`; `sec/fulltext.py` (`parse_entities`, `SearchResult.complete`); migration engine 0014; `scripts/run_themes.py`; templates `themes.html`, `theme.html`, `theme_filers.html`, `tabs/themes.html`, `_theme_macros.html`; tests `test_themes.py`, `test_ui_themes.py`, live `tests/live/test_m02_live.py` (label m02-probe).
- Probe facts: entity_filter 30 buckets; forms=10-K includes 10-K/A; NEAR → 0 through the API; form.gz present.
- First run: 443 SEC requests for 37 phrases × 9 windows (10-K); 32 form indexes (~24k tracked-family rows per quarter). One persistent EFTS 500 ("advanced packaging" 2020) → half-window retry added afterwards.
- Generic phrases seen: "domestic manufacturing" (replaced), "behind-the-meter" (dropped), "HBM" may collide with other acronyms/tickers, "advanced packaging" may include non-semiconductor packaging → part 6 industry-spread test (SIC per hit is stored in `fulltext_hit.sics`).
- Not done in part 1 (later parts): weekly/seasonal scheduling (part 2/6), 10-Q/8-K families by default (run with `--families`), phrase tests and proposals (part 6).
- Visual check: scratch data in `.claude/launch.json` config `ui-scratch` (port 8799; data dir = session scratchpad — change the path for a new session).

### Part 2 — Plumbing (built 2026-10-09, D-M02-18, D-UI-18)
- Code: `themes/proposals.py` (propose, flush_overflow, overflow, apply, queue_still_track, suggest_promotion), `themes/tiers.py`, migration engine 0015, `review.m02_action`, `refresh._process_tracked`, `prices/store.tracked_rotation`, `prices/tiingo` `hourly_budget`, `run_refresh.py` `waiting_summary`/`show_info`; UI `_side.html`, `tabs/themes.html` tier box, `/c/<ticker>/tier/<action>`, review week header + M02 payload view + guide rows, Themes page waiting list; tests `test_m02_plumbing.py`, `test_ui_themes.py`.
- For generators (parts 3–7): call `proposals.propose(engine, kind, key, reason, payload, now, cik=…)`. Put `companies` (int) and `money_flow` (bool) in the payload so material-change re-raising works; `samples` (list of quotes) and `why` render on the item page; `phrase_id`/`theme_id` let accept/reject set status. Keys must be stable across runs (e.g. `theme:phrase`, `cik`, `accession`).
- Tracked names are synced on first sight; their prices start in the rotation on the next run.
- Not built: reopen for M02 items (would need undoing tier/status changes); evidence rules for promotion (parts 3/5/6).

### Part 4 — Call guidance (built 2026-10-09, D-M02-22)
- Code: `calls/alpha_vantage.py`, `calls/transcripts.py` (fiscal_quarter, plan, store_transcript, fetch_due, queue_reminders, import_files), `calls/ir_inbox.py`, `calls/step.py`; `guidance/calls.py` (scan_call, scan_calls, management_turns), `guidance/sources.py` (labels), `guidance/parse.py` guidance-5 (`parse_call`, `clause_of`, anchored periods, CY), `guidance/changes.py` (definition changed, call repeats skipped); migrations engine 0016, corpus 0006; `scripts/run_calls.py`; `run_refresh.py` `calls_step`; prompt `guidance_reasons_2.md`; UI guidance tab, reader, source, search, review item (pickup/ingest routes); tests `test_calls.py` (synthetic transcript in AV shape).
- Dependency: pypdf (D-M02-21).
- Live check (owner): `uv run python scripts/run_calls.py --import-probe --fetch 6` → imports the 7 probe replies, scans releases (guidance-5 re-scan), requests ≤ 6 due transcripts (newest releases first), scans calls; log `logs/calls_*.txt` lists speaker titles per role, rows, matches, conflicts and capex sentences sent to review. Check: management/analyst split is right; MSFT/ORCL/AMZN capex rows; fiscal labels match AV for NVDA (January FYE) and AAPL.
- Expect from the real corpus (LESSONS: each live scan found new wording): new spoken capex phrasing → review items; role titles not covered by the rules → "call other" (never parsed) — extend `role_of` from the log.
- Not built: auto-fetch from allowed IR sites (D-M02-21 dropped it), DOCX/PPTX, owner override of "definition changed", stale flag "may have been updated on the call" (part 3), reopen of a `downloaded` item.
- Live check 1 (2026-10-09, logs/calls_20261009-122055.txt): roles right in all 9 transcripts (Alpha Vantage titles look like "Analyst (Barclays)", "Analyst, UBS", "Chief Financial Officer"); 48 transcripts left in the queue (16 companies × ~4 quarters, ~20/day). Problems found and fixed in guidance-6 (D-M02-23): retold prior guidance, third-party capex, segment revenue, bounds, year-ago "from", noun "guide", period from the previous sentence, review noise, deliveries 8-K as release date, re-linking, warrant ticker. Re-check: same command without `--import-probe` (`--force` re-scans everything locally; `--fetch 6` continues the queue).

- Live check 2 (2026-10-09, logs/calls_20261009-132915.txt): 20 transcripts; fixes D-M02-25 (guidance-7). Still to explain: Alphabet's call capex (0 rows) — the next log lists capex sentences that produced nothing.
- Live check 3 (2026-10-09, logs/calls_20261009-134554.txt + refresh run 8): Alphabet explained by the capex-not-stored lines; fixes D-M02-26 (guidance-8). Alpha Vantage limit reached for the day; 39 transcripts queued.
- Live check 4 (2026-10-09, logs/calls_20261009-144011.txt): round-3 fixes confirmed; D-M02-27 (guidance-9). PR opened after this round.

### Part 4b — Guidance accuracy loop (built 2026-10-09, D-M02-24)
- Code: `guidance/labels.py` (label_row, label_span, current_row, wrong_keys, store_skips, queue_audit, check_plausibility, accuracy, check_labels), `llm/call_check.py` + prompt `call_check_1.md`, `guidance/calls.parse_document`; ParseResult.skipped_spans; scans skip labelled-wrong rows and store skips; calls step runs plausibility + weekly audit; `review.label_action`, `review.mark_wrong`; UI `guidance_wrong.html`, `call_check.html`, review item check view, Runs "Guidance accuracy"; `run_calls.py --check-labels`, `--gemini-check DAYS [--yes]`; migration engine 0018; tests `test_guidance_accuracy.py`.
- Every build session that touches the guidance parser: run `run_calls.py --check-labels` (owner) and read new labels in the log before changing rules; paraphrase new cases into fixture tests.
- Review load: ~8 audit items/week plus plausibility flags (only on new outliers).

### Part 3 pre-check (2026-10-09, D-M02-19) — read before building part 3
- Order: build part 4 first. Part 3 then adds: derived spenders from frames (capex tags `PaymentsToAcquirePropertyPlantAndEquipment`, fallback `PaymentsToAcquireProductiveAssets`; ~30 frame requests for 2019→now; `sec/frames.py` exists), candidate proposals for top spenders/growers via `proposals.propose(..., "m02_candidate", cik, ...)`, spender→theme quote link (new review kind needed, e.g. `m02_spender`; the customer–supplier `m02_link` does not fit), Capital allocation block, supplier RPO view, per-spender contributions (D-M02-15).
- New concepts for `sec/xbrl_facts.py` concept map: finance_lease_principal, debt_issued, debt_repaid, equity_issued, buybacks, tax_withholding, dividends (check tag names against real company facts in the live check; facts parser version bump → re-sync).
- Funding coverage = OCF ÷ capex (own definition), trailing four quarters; net debt/equity = issued − repaid, same window; labelled association, not cause.

### Part 3 pre-check 2 (2026-10-09, after part 4; D-M02-28…31) — the build checklist
Decisions in M02_THEMES.md; this is what the build needs.
- **Inputs from part 4 (D-M02-22…27):** guidance rows carry `origin` (release/call/ir), `grade`, `kind` (range/plusminus/approx/point/direction), `bound` (floor/ceiling), `clause`, `matched_accession`, period labels FY…/CY…; owner corrections (`source='owner'`) win; labels (`guidance_label`) — rows marked wrong are already gone. Plausibility (`guidance/labels.py`) already reads `series`.
- **Money-flow guidance (D-M02-28):** per spender and guided period, the latest statement (any grade, labelled); growth by form — range midpoint + low–high, approx as stated, floor "≥ +X%" ranked at its minimum, ceiling/direction listed below the ranking; calendar-basis guidance (today Microsoft) compares with summed calendar quarters, "not comparable yet" until four exist.
- **Freshness (D-M02-30):** six states — restated / not restated / call not stored yet / call unavailable — not checked / latest results not read yet / no capex guidance given; "company gives no outlook yet" for explicit refusals (these sentences are already skipped with reason "says no guidance is given" in `guidance_skip`); ended periods → guided-vs-actual. Inputs: `filing` (Item 2.02), `guidance_scan`, `call_fetch` (empty/failed, reminder_queued), `call_document`.
- **Actuals (D-M02-29):** recipes by clause; `config/capex_definitions.toml` overrides (Amazon: `PaymentsToAcquireProductiveAssets` − `amzn:ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives`); new XBRL concepts `finance_lease_principal` (`FinanceLeasePrincipalPayments`), `finance_lease_rou_new` (`RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability`); company extension tags need a facts-parser path for non-us-gaap taxonomies (check `sec/xbrl_facts.py` `iter_facts`). **Stated actuals:** past-tense capex sentences ("CapEx was $44.9 billion in the second quarter"; already listed as "CAPEX NOT STORED" in run_calls logs) parsed into a new table (never guidance), reconciled per quarter within 1%; Microsoft labelled approximate.
- **Capital allocation (D-M02-31):** OCF, capex (recipe), OCF ÷ capex, debt raised/repaid (all mapped tags: `ProceedsFromIssuanceOfLongTermDebt`, `ProceedsFromIssuanceOfDebt`, `ProceedsFromIssuanceOfSeniorLongTermDebt`, `ProceedsFromRepaymentsOfShortTermDebt`, `ProceedsFromShortTermDebt`, `RepaymentsOfLongTermDebt`, `RepaymentsOfDebt`, Microsoft's maturity tags), equity issued, buybacks, withholding, dividends (two tags); coverage vs `NetCashProvidedByUsedInFinancingActivities` < 80% → "partial" + `m02_tag` review items (map as debt raised / repaid / equity / other / ignore; us-gaap mappings global, extensions per company; stored in DB, undoable, listed on Runs). TTM + last FY side by side.
- **Candidates and links (D-M02-30):** D-M02-20 (6) thresholds; weekly cap 10, largest first; `m02_spender` items from filings, releases and calls (call sentences grade B).
- **Supplier RPO:** D-M02-19 (4).
- **Review load:** ≈ 8 guidance checks/week + ≤ 10 M02 items + `m02_tag` items (only on coverage gaps).
- **Open at build start → settled D-M02-32 (option a + b, stated figure shown when the recipe is approximate or off):** company extension tags (Amazon's `amzn:ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives`, its financing-obligation repayments; Microsoft's maturity-based debt tags are us-gaap) are probably **not** in SEC's companyfacts API, which carries standard taxonomies only (`sec/xbrl_facts.iter_facts` stores whatever taxonomies the JSON has) — verify on Amazon's stored facts first. If absent, options: (a) fetch the filing's XBRL instance / R pages for override-recipe companies only (a few requests a quarter); (b) use gross purchases for Amazon, labelled "approximate: excludes proceeds from sales and incentives" (gap ≈ 2%); (c) take the stated actual from the call (stated-actuals table) as Amazon's actual. Same question applies to `m02_tag` discovery of extension financing lines. Also mock up the per-spender money-flow view on stored data before building it (LESSONS, D-UI-4).
- **Live check (owner, one command at the end):** frames + facts re-sync for watchlist/tracked spenders; print per spender: guidance line with freshness state, recipe and reconciliation result, capital-allocation block with coverage %, candidates queued. Requests: ~30 frames + facts re-sync (SEC, minutes).

### Part 3 — Money flow (built 2026-10-09, D-M02-32, -33)
- Code: `src/engine/moneyflow/` (instance, periods, stated, actuals, guided, allocation, spenders, links, views, step); migration engine 0019; `config/capex_definitions.toml` (AMZN); `scripts/run_money.py`; `run_refresh.py` `money_step` after the calls step; UI tab `money` (`tabs/money.html`), theme page section, Runs "Cash-flow tag mappings" with undo (`POST /money/tag-map/<id>/undo`), review guide rows and action labels; tests `test_moneyflow.py` (18).
- Mock-up approved by the owner before the build (company tab + theme section, as built). Visual check on scratch data (META reconciled $31.08B; AMZN stated shown, recipe ≈ +2.1%; MSFT "not comparable yet (2/4)"; theme ranking; m02_tag map → coverage 62% → 100%, undo reopens).
- No facts re-sync needed: recipes and allocation read raw `fact` rows (companyfacts already stores every us-gaap tag); new concepts were not added to the concept map.
- **Live check (owner):** `uv run python scripts/run_money.py` → logs/money_*.txt. SEC: XBRL instances for AMZN (override) and any company under 80% coverage (≤ 12 filings each, first run only) + annual capex frames for the last two years (≈ 6 requests). Check: per company the guidance line and freshness state, actual quarters (recipe vs stated, reconciled/gap), allocation coverage %, link sentences queued, spender candidates. Expect new stated-actual wording (stated-1 is narrow) and financing tags to map.
- Live check 1 (2026-10-09, logs/money_20261009-181912.txt): instances and coverage worked (AMZN 62% → 100% with extension facts; GOOG 17%, MU 10%, META TTM 35%, INTC 45%, ORCL TTM 44% → `m02_tag` items); 19 spender candidates waiting (weekly cap used by link items); fixes D-M02-34. Re-check: `uv run python scripts/run_money.py --no-sec` (local, seconds).
- Live check 2 (2026-10-09, logs/money_20261009-182719.txt, no SEC): D-M02-34 fixes confirmed (META CY2026 +90%; AMZN fiscal year to 2025-12-31; MU/TSLA recipe kept, statement flagged; TSLA restated; MSTR n/m). PR opened. Watch: AVGO FY2026 Q4 capex guidance $1.4B (+491% vs a $237M quarter) — check the call sentence (plausibility/weekly sample).
- Open: TTM windows need quarterly cash-flow facts (FY only otherwise); `m02_capex_gap` has only "Noted"; stated-actual parser has no accuracy loop yet (labels are guidance-only).

### Money flow — capex guidance (D-M02-5)
- Reuse: `guidance/ledger.py` (metric `capex`), `guidance/changes.py` (raised/lowered…), `sec/xbrl_facts.py` concepts `capex` (`PaymentsToAcquirePropertyPlantAndEquipment`, fallback `PaymentsToAcquireProductiveAssets` — the fallback tag must be shown, M00_SEC_DATA open item) and `rpo`.
- Needed: concept for finance-lease principal (`FinanceLeasePrincipalPayments`) so Meta-style "capex incl. finance-lease principal" can be rebuilt for guided-vs-actual; parser keeps the "including/excluding …" clause per capex row; `changes.py` gains "definition changed" when clauses differ.
- 2026 reference values for tests and sanity checks (S80): Meta CY2026 $130–145B (release, incl. finance-lease principal; was $125–145B); Alphabet $195–205B (call; was $180–190B); Amazon ~$220B (call; was ~$200B); Microsoft ~$175B CY2026 (call; drop from ~$190B is the lease reclassification); Oracle FY27 $90–95B (secondary).
- Owner note: weighting of capex as a buy signal for the spender is revisited later (D-M02-5).
- Purchase obligations are not in the XBRL concept map yet; ≥10% customers are dimensional (not in company facts) → text only.

- Capex funding component (owner): capex vs operating cash flow, and debt/share issuance in the same period (XBRL concepts to add: operating cash flow, debt proceeds, share issuance proceeds — check the concept map).

### Part 5 — Suppliers L0–L3 (built 2026-10-09, D-M02-35, -36)
- Code: `src/engine/supply/` (aliases, find, links, scan, gold, step), `src/engine/llm/supply_labels.py` + prompts `supply_labels_1.md`, `input_categories_1.md`; `config/aliases.toml`; migration engine 0020; `scripts/run_suppliers.py`; `run_refresh.py` `supply_step`; UI `/m02/labels` (blind card), Money flow tab "Suppliers and customers named in filings", Runs "Supplier-link precision set", review guide example rows; tests `test_supply.py` (12).
- **Live check (owner):** `uv run python scripts/run_suppliers.py --customers NVDA,META,MSFT --probe` → logs/suppliers_*.txt. SEC: L3 ≤ 10 Item 1.01 filings (index + EX-10s), L2 4 phrases × each alias of the three customers (~32 searches), ≤ 30 hit documents, probe ≤ 10 pages per bare alias (counts only). Check: L2 phrase hit counts vs probe (c) "not found by the targeted phrases" → decide (c); sample pairs read right (direction, share %); L1 names from NVIDIA's own 10-K (TSMC, Samsung, SK hynix, Micron …).
- Live check 1 (2026-10-09, logs/suppliers_20261009-193907.txt): fixes D-M02-37; owner chose the option (c) trial for NVIDIA (D-M02-38).
- Next (owner): `run_suppliers.py --rescan --customers NVDA` (re-reads stored documents with the fixed rules, queues and fetches the first 30 trial filings; repeat the command without --rescan for the rest, ~4 runs, or let the refreshes do it) → then `--label-set`.
- Live checks 2–3 (2026-10-10): fixes D-M02-39, D-M02-40; precision set labelled and measured (Gemini supply precision 82%, recall 100%, direction 77%); (c) trial 2/10.
- Then: `--label-set` → label at /m02/labels (~15–20 min) → `--gemini-labels --gold` (estimate, `--yes`) → accuracy on the Runs page and in the log. 5b: `--gemini-inputs NVDA` (estimate first).
- Open: aliases cover the watchlist and common semiconductor/hardware suppliers only (extend `config/aliases.toml`); L1 matches only alias names (unknown supplier names are not found); Exhibit 10 of 10-K/10-Q not read (8-K Item 1.01 only).

### Supplier discovery L0–L3 (D-M02-7)
- L2 is the main free method: EFTS phrase = the customer's name (one quoted phrase per query, D-SEC-14), forms 10-K/10-Q, then fetch hit documents and find the sentence with FTS NEAR(name, customer / "accounted for" / "% of"). EFTS returns no text (S56), so each hit needs a document fetch (budget it).
- L1: customer's own Item 1 / 1A passages naming suppliers (check NVIDIA's 10-K wording in the stored corpus at build).
- L3: 8-K Item 1.01 events already catalogued (`events.py`); Exhibit 10 documents are not ingested by default (D-SEC-7 ingests primary + EX-99.1) → add EX-10.* for Item 1.01 filings of linked companies.
- Each link = review item until the owner confirms; rung + grade + quote stored; direction (who supplies whom) shown explicitly.
- Later rungs L4–L8 listed in D-M02-7.

### Part 5b pre-build note (2026-10-10) — read first in the part-5b conversation
- Decisions: D-M02-41 (kinds, purpose), -42 (sources, checked-automatic numbers, review-guide examples), -43 (display, loop cases 1–4 on confirmed links, sizing ratios, weekly-digest alerts), -44 (placement, cost).
- Probe first (live, owner): which watchlist companies file 13F (expected NVIDIA); 13F information-table format and the January 2023 dollar unit; 13D/13G discovery through filing indexes; XBRL tag names for financing receivables and allowances (`FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss` seen in filings; check the allowance and doubtful-accounts tags in stored facts).
- Reuse: `supply/links.py` pattern (pairs, sides, `seen_at`/`stale`, prune, follow decisions), `supply/find.py` noise rules (now become K1 evidence: `_SECURITIES`, `_DEAL`), `sec/events.py` item codes, `sec/documents.py` exhibit fetch, `sec/xbrl_facts.build_concept` for ad-hoc tags (`moneyflow/periods.tag_points`), `themes/proposals.py`, `guidance` "wrong?" button pattern for records.
- Mock up the Money flow section and the review items (with the owner's requested worked examples) before building (LESSONS).

### Part 5b — probe (2026-10-10, logs/probe_financing_20261010-221526.txt; `scripts/probe_financing.py`)
- **13F filers among 18 companies: AMZN, GOOG, INTC, NVDA** (not NVIDIA only). Index lists `primary_doc.xml` (cover: `periodOfReport`, `tableEntryTotal`, `tableValueTotal`, other managers) and the information table (filename varies: `infotable.xml`, `information_table.xml`, `form13fInfoTable.xml`, `<acc>-2761.xml`; type "INFORMATION TABLE"); each listed twice (raw + XSL rendering). Row fields: nameOfIssuer, titleOfClass, cusip, value, sshPrnamt, sshPrnamtType, putCall, investmentDiscretion, otherManager, voting Sole/Shared/None. Sum of values = `tableValueTotal` in all 7 read. **Unit confirmed:** thousands before 2023 (GOOG 2022-09 total 1,958,351 = $1.96B; AMZN 2020 Vital Farms 40,578 for 1.6M shares), dollars after. One issuer can have several rows (Intel's Joby, two other managers) → sum by CUSIP. INTC's 1995 13F is a paper record (no XML). NVDA 2026-06-30: Intel 214.8M sh $30.0B, SpaceX $21.0B, CoreWeave $4.7B, Coherent, Nokia, Synopsys, Nebius, Generate Biomedicines.
- **13D/13G:** 1,674 filings listed under the 18 companies (both as filer and as subject; mostly institutions about them). The index header names roles (`companyName">… (Filed by)` / `(Subject)`). XML schedules (forms `SCHEDULE 13D/G[/A]`, from Dec 2024) carry `issuerCik`, `issuerCusipNumber`, `issuerName`, per reporting person `reportingPersonName`, `reportingPersonBeneficiallyOwnedAggregateNumberOfShares`, `classPercent`, `typeOfReportingPerson`, `eventDateRequiresFilingThisStatement`. Examples: Amazon 22.9% of X-Energy; Google 7.2% of SpaceX; Mubadala 72.8% of GFS. Older `SC 13D/G` are text documents.
- **XBRL:** financing-receivable tags only at BA (Boeing Capital) and TSLA. Trade-receivable allowance (`AllowanceForDoubtfulAccountsReceivable[Current]`) current at AMZN, MSFT, ORCL, GOOG, BA, MRVL, SPCX, MSTR; the others stopped tagging it 2014–2021. `GuaranteeObligationsMaximumExposure`: NVDA $108.5B, AVGO $29.0B, GOOG $7.6B, TSLA $4.07B. Equity investment book: `EquitySecuritiesFvNi` (NVDA $42.8B, META $3.5B), `EquitySecuritiesWithoutReadilyDeterminableFairValueAmount` (AMZN $122.3B, GOOG $124.3B, NVDA $47.9B, META $20.8B, MSFT $12.4B, INTC $8.2B), `EquityMethodInvestments` (MSFT $12.0B, META $9.4B, GOOG $2.3B), NVDA `…NetAdditionsDisposals` $13.1B.
- **Text finders (draft regexes, stored documents of the 18):** K1 2,446 sentences, 31 naming another known company (Intel ↔ NVIDIA $5.0B share sale, in 10-K and EX-99.1); K2 81 / K3 74 / K4 78 sentences, **none naming a known company**; K6 209, one named (Tesla's equity-method stake in SpaceX). The counterparties of the motivating cases (CoreWeave, OpenAI, AMD) have no stored documents. 8-K Item 3.02: MU 10, TSLA 11, MSTR 8, INTC 7, MRVL 4, others ≤ 3.

### Part 5b — Financing links (built 2026-10-10, D-M02-45, D-M02-46)
- Code: `src/engine/financing/` (issuers, thirteenf, schedules, find, scan, links, credit, views, step); migration engine 0023; `scripts/run_financing.py`, `scripts/probe_financing.py`; `run_refresh.py` `financing_step` after the supplier step; review kinds `m02_finlink`, `m02_13f_issuer` (map/dismiss, form field `target`), `m02_fin_check` (keep/wrong), `m02_fin_alert` (noted); UI Money flow sections "Financing and equity links" and "Credit quality and investment book", POST `/fin/holding/<id>/wrong`, Runs "Financing records marked wrong" with undo, review-guide rows with worked examples; tests `test_financing.py` (16).
- Mock-up approved by the owner before the build; visual check on scratch data with the probe's real NVIDIA 13F (Intel $29.99B, SpaceX $20.98B, CoreWeave $4.70B with loop 1 on a confirmed supply link, CoreWeave backstop to review, grouped smaller holdings, credit series with DSO and guarantee alerts, issuer map → row resolved).
- **Live check (owner, one command):** `uv run python scripts/run_financing.py` → logs/financing_*.txt. SEC, first run (~450 requests, a few minutes at 5/s): 13F of AMZN, GOOG, INTC, NVDA for 8 quarters (+ amendments), ~120 13D/13G index headers + XML of relevant ones, ≤ 10 Item 3.02 filings, ~5 phrases per company name (~120 searches), ≤ 30 hit documents. Check: 13F totals and "held" reasons; unresolved issuers (expect GV biotech names); 13D/G stakes (Amazon → X-Energy 22.9%, Google → SpaceX 7.2%); text pairs and their directions (Intel ↔ NVIDIA K1, any CoreWeave backstop); credit-series lines per company; loops. Expect new wording → two or three rounds (`--rescan` re-reads locally, `--no-sec` skips SEC).
- Live check 1 (2026-10-11, logs/financing_20261010-235913.txt): 13F 32 filings / 406 holdings (342 automatic, 64 unresolved → 18 issuer items), 9 relevant 13D/G stakes (Amazon → X-Energy 22.9%, NVIDIA → CoreWeave 11.5%, NVIDIA → Nebius 9.3%, Intel → Mobileye 79.8%), 120 searches (25 hits for "warrant to Amazon.com"; 23 hit documents still queued), 119 passages / 29 pairs (all overflow: weekly cap), 5 credit alerts. Fixes D-M02-47 (DSO rule and bands chosen by the owner). Re-check: `uv run python scripts/run_financing.py --rescan` (re-reads locally, retries unresolved issuers, fetches the next 30 hit documents and the "unsold capacity" search).
- Live check 2 (2026-10-11, logs/financing_20261011-002536.txt): D-M02-47 fixes confirmed (issuers, exits, warrants as K2 with share counts, Marvell $2.0B, registry names, no Microsoft DSO alert; "unsold capacity" found AMD → Rackspace); fixes D-M02-48. 33 link items wait in the weekly overflow (cap 10/week). Re-check locally: `uv run python scripts/run_financing.py --rescan --no-sec`.
- Live check 3 (2026-10-11, logs/financing_20261011-003102.txt, local): D-M02-48 confirmed; three wording fixes (rights-of-refusal order, "represents and warrants", filer's own name) added to D-M02-48. 30 link items wait in the weekly overflow. PR opened.
- Live check 4 (2026-10-11, logs/financing_20261011-003823.txt, local re-read): the three live-check-3 fixes confirmed (13 passages removed); 27 link items in the weekly overflow. Known wrong passages left for the owner's review: Silvaco names NVIDIA beside Micron's convertible note; ATSG's buyback of Amazon's shares; Allegiant reporting Sun Country's warrants.
- Open: aliases bound the text finders (private companies such as OpenAI have no entry yet — add by hand); old text 13D/G not read; the amount is the sentence's first $ figure (may be a price per share — the owner sees the quote).

### Part 6 pre-build note (2026-10-10) — read first in the part-6 conversation
- Scope (row above): corpus phrase mining (rising 2–3-grams per year, boilerplate dropped), phrase tests (EFTS hits, ≥ N distinct companies, industry spread from `fulltext_hit.sics`, 3 sample passages, zero shown as zero), Gemini use case 4 (names a cluster, suggests variants — re-tested), `m02_phrase` / `m02_theme` / `m02_candidate` proposals with the section + quantified rule (watch tier otherwise), crowding flag (N-1A/485APOS mentions per window), first-mention flags (name change 8-K 5.03, offerings S-1/S-3/424B, reverse merger, micro-cap), seasonal schedule (~Apr 15, ~May 20, ~Aug 19, ~Nov 19).
- Open at build start (D7, ask first): N distinct companies for the phrase test; the micro-cap line for first-mention flags (both listed in M02_THEMES open questions); whether the seasonal pass runs inside the logon refresh or only by command (PC off overnight, 3-h task limit, D-M02-12).
- Reuse: `themes/breadth.py` (EFTS windows, lower bounds), `themes/proposals.py` (propose, weekly cap), `search/passages.py` (passages + boilerplate flag, D-SRCH-20), `llm/` request/verify pattern (`supply_labels.py` is the newest example), `fulltext_hit.sics` for industry spread.
- Lessons from parts 3–5: mock up screens with real-shaped data before building; each live log found new wording — plan two or three live rounds; regexes go in with the Edit tool, never heredocs (escapes break); a passage store needs a re-read path (`--rescan`-style) from the first version; keep an answer key out of re-read deletions.

### Phrase mining and tests (D-M02-8)
- Corpus n-gram counts per year over stored passages (`search/passages.py` output); flag rising 2–3-grams; drop stop-phrases and boilerplate (forward-looking-statement text, D-SRCH-20).
- EFTS breadth per phrase via `fulltext.count_by_window` (distinct companies need all hits fetched; EFTS aggregations return only top ~30 entities — live probe at build).
- Industry spread from hit SICs (`fulltext_hit.sics`).
- Gemini use case 4: prompt gets the mined cluster + sample passages; output = name + variants, each variant re-tested.

### Link labelling (D-M02-9)
- Hand-label ~30 passages first (fixture), measure Gemini precision + direction accuracy; record in this log.
- Real example for tests: NVIDIA FY2026 10-K names foundries TSMC, Samsung; memory SK Hynix, Micron, Samsung; assembly/test Hon Hai, Wistron, Fabrinet; CoWoS vendor unnamed. Commitments 2026-01-25 $95.2B manufacturing/supply/capacity; Q2 FY27 CFO commentary: supply commitments $119B → $279B, mostly memory (L4 example).
- Use case 5b prompt: Item 1/1A passages of one company → input categories with quotes.

### Digest and review items (D-M02-10)
- Reuse: `review_queue` table (module_id 'M02', kind, payload JSON), `engine/review.py` actions pattern, `/review` filters, guide panel (D-UI-15). New kinds: m02_theme, m02_phrase, m02_candidate, m02_link, m02_input.
- Suppression key per proposal (theme/phrase/company/link) + last shown components → re-raise only on material change (distinct filers doubled, new hard money-flow evidence).
- Weekly header = a grouping label on the queue page (no separate item); cap 10/week, overflow listed in the Themes tab.
- Seasonal schedule: ~Apr 15; ~50 days after Mar 31, Jun 30, Sep 30 (i.e. ~May 20, Aug 19, Nov 19). Denominator = distinct filers of the form family in the same window (EFTS total for a near-universal phrase, or SEC filing-count data; decide at build — S88).
- Crowding: EFTS forms N-1A, 485APOS (+ 485BPOS?) with the theme phrase, per window.

### Tracked tier (D-M02-11, D-M02-12)
- Tables: tier membership (cik, ticker, tier tracked/promoted, theme ids, reason, added_at, added_by, last_evidence_at) — owner id per U3 where personal.
- Refresh (runs at logon, PC off overnight): universe = toml core ∪ promoted (full jobs) and tracked (filing index + XBRL facts on new filings); prices: core + promoted daily, tracked in a 3-day rotation (by cik mod 3 or oldest-bar-first), soft cap ~150 tracked; price step ≤ 40 req/h so the app keeps 8/h (`prices/tiingo.py` budget check reads `fetch_log`); `scripts/run_refresh.py` `prices_step` today takes the resolved watchlist only.
- Keep refresh write transactions short (app writes during the run; busy_timeout 5 s). Task limit 3 h (`register_tasks.ps1`).
- End-of-run summary box (ctypes MessageBox already used by `ask_yes_no`) when downloads or review items are waiting.
- Side panel already reserves "Tracked" (M00_UI); add core/promoted labels.
- Review kinds: m02_candidate (accept → tracked), promotion suggestion, still-track review (12 months without new evidence).

### News and official feeds (D-M02-13)
- Reuse ideas (not code) from `reference/old_engine/ir_feeds.py`: feedparser-based fetch, entry cleaning, recency filter, keyword match. Adds a dependency (feedparser) → `uv add` asks the owner.
- IR RSS URLs (checked 2026-10-08): Q4 Inc `/rss/pressrelease.aspx` — investors.micron.com, investor.nvidia.com, investor.atmeta.com, investors.boeing.com (headline/link/date, no description); Notified `investors.gf.com/rss/news-releases.xml` (snippets); Intel `www.intc.com/news-events/press-releases/rss`; NVIDIA newsroom `nvidianews.nvidia.com/releases.xml`. Discovery rule: `<link type=rss>` on the press page, then vendor patterns. Store per company in config with date checked.
- Trade-press feed URLs: semiengineering.com/feed/, eetimes.com/feed/, servethehome.com/feed/, tomshardware.com/feeds.xml, datacenterdynamics.com/en/rss/, datacenterfrontier.com (`__rss/website-scheduled-content.xml?input={"sectionAlias":"home"}`), spacenews.com/feed/, nasaspaceflight.com/feed/, quantumcomputingreport.com/feed/, thequantuminsider.com/feed/, therobotreport.com/feed/.
- Finnhub `/company-news?symbol=&from=&to=` (key header), Massive `/v2/reference/news?ticker=` (5/min). Grade map by source domain in config.
- Official: arXiv API (1 req/3 s, one connection; count new preprints per phrase per month), USAspending `/api/v2/search/spending_by_award/` (recipient filter; POST JSON), Federal Register `/api/v1/documents.json?conditions[term]=`, Congress.gov (`CONGRESS_API_KEY`).
- Each feed behind one adapter (U7), its licence in DATA_SOURCES.md; tests use recorded fixtures only.

### Search inputs (D-M02-14)
- Live probe (owner runs, `scripts/run_live.py` label to add): EFTS aggregations (`entity_filter` bucket count, `sum_other_doc_count`?), `NEAR(n)` and OR through the API, `forms=10-K` vs 10-K/A, page size 100, `from` > 10,000 error.
- `fulltext.count_by_window` gains `max_pages` (10) and a lower-bound flag; companies from `entity_filter` when capped.
- Denominator: `full-index/{year}/QTR{n}/form.idx` (fixed-width; form, company, CIK, date, file) → distinct CIKs per form family per window; form families: 10-K (+10-K405 pre-2003, 10-KT?), 10-Q (+10-S if adopted, S88), 8-K, 20-F/40-F, N-1A/485APOS (crowding).
- Section tagging uses stored sections (`sec/sections.py`, items-1) and FTS5 NEAR over passages; "quantified" = a number, $, % or money word (revenue, capex, orders, backlog, million, billion) within ~10 words.
- Fetch queue table (accession, reason, queued_by, queued_at, fetched_at); `scripts/fetch_queued.py`; refresh drains it.

### Build requirements from the failure-mode table (D-M02-15)
- Store `discovered_at` on every phrase, theme, link and candidate (point-in-time backtests).
- First-mention flags: 8-K Item 5.03 (name change), S-1/S-3/424B* within ±90 days, reverse merger (8-K Items 2.01 + 5.01/5.06 shell), market cap below a micro-cap line (from prices × shares; line set at build).
- Per-spender contributions in every money-flow view.
- L2 alias table per customer (legal name, short name, ticker-free aliases) + nearby customer/revenue wording.
- News dedupe key (normalized URL; else title + date + company).

### Call guidance from IR documents (D-M02-6, DS1) — design notes (built as part 4, see above)
- Also owns (moved from part 3): the capex "including/excluding …" clause tag on ledger rows and the "definition changed" label in `guidance/changes.py`.
- Settled (D-M02-21): lean fallback (reminder + PDF pickup, pypdf); use case 1 may read call passages; transcripts in corpus/search/reader; source label on every call-derived item + "forecast, not a commitment" note on all guidance (Guidance tab, money flow, Gemini output, search hits).
- Settled (D-M02-20): direction-only rows for directional guidance; release wins over call; all metrics from management turns, capex-only review items; tracked names get releases + transcripts; Alpha Vantage budget ≤ 20/day for runs, ~5 interactive; import probe responses; dev sample of one quarter across ~11 companies (~6 new calls), backfill later in the background. Guidance schema needs a direction-only kind (no low/high) — migration.
- Main spenders first: Alphabet, Amazon, Microsoft, Oracle (Meta's capex is in its release).
- Step 1: owner runs `uv run python scripts/probe_alpha_vantage.py` (7 requests; summary in logs/probe_av_*.txt, raw JSON in data/probe/alpha_vantage/). Answers: free-key access, coverage (AMZN, MSFT, ORCL, AAPL, TSLA), calendar vs fiscal `quarter`, capex wording present.
- **Result (logs/probe_av_20261009-000758.txt):** 7/7 HTTP 200, no premium/limit messages. Response `{symbol, quarter, transcript: [{speaker, title, content, sentiment}]}`; 24–61 turns, 35–57k characters per call. `quarter` = company fiscal label: MSFT 2026Q2 → FY26 Q2 call ("Capital expenditures were $37.5 billion in this quarter…"), MSFT 2026Q4 → July 2026 call ($41 billion), ORCL 2026Q3 → March 2026 call (analyst asks about FY2027 capex). ORCL 2027Q1 (Sept 2026 call) → `transcript: []` (empty = not available yet; missing, never "no guidance"). AAPL 2026Q3: no capex wording (Apple gives none). Raw JSON in data/probe/alpha_vantage/ (owner's machine only).
- Build notes from the probe:
  - Map ledger periods directly: company label FY2026 Q4 ↔ `2026Q4` (no calendar conversion).
  - Parse **management turns only** (title is an officer/IR role; skip Operator and analysts — analysts' questions carry capex numbers too).
  - Spoken guidance is often directional ("heavy CapEx the next few years", "FY27 capex to grow") → part-4 design question (direction-only row vs review queue; see M02_THEMES open questions). Expect new parser wording → review queue first.
  - `sentiment` per turn is a vendor score: stored, never used as a signal (unverifiable).
  - Empty transcript → retry on later runs for ~30 days, then queue `m02_ir_download`.
  - Budget: 25 requests/day → backfill 16 companies × 4 quarters ≈ 3 days; ongoing ≈ 16 per quarter. Key `ALPHA_VANTAGE_API_KEY` goes in the query string (Alpha Vantage requires it): never log URLs.
  - Fixtures: synthetic JSON in the same shape (vendor transcripts stay off GitHub).
- If Alpha Vantage fails: IR documents. Checked 2026-10-08 — transcripts: MSFT (DOCX, cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/TranscriptFY26Q4.docx), GOOGL (PDF, s206.q4cdn.com/479360582/files/doc_events/…), META (PDF, s21.q4cdn.com/399680738/files/doc_financials/<yr>/q<n>/), NVDA and BA (FactSet ©); prepared remarks with capex: MU (s25.q4cdn.com/621799436/…/Q4-FY26-Prepared-Remarks.pdf), INTC; CFO commentary: NVDA; Amazon audio only (DS9); Oracle/Apple none. Q4 Inc runs 10 of 13 sites and builds file links with JavaScript (needs a rendered page or the owner's download).
- Terms (not legal advice): NVDA, AAPL, INTC, BA, ORCL, AMZN bar robots; MU only above human pace; Google via robots.txt; MSFT, MRVL, GFS allow personal copies. Owner decision (2026-10-08): honour the terms — automatic fetch only for MSFT, MRVL, GFS (MU at human pace); all others via the **browser-download inbox**.
- Inbox design (build): folder from settings (default `data/inbox/ir/`, U5); the owner saves a file there; an ingest step (script and a UI page) asks or infers ticker, document type (transcript / prepared_remarks / cfo_commentary / slides), company period label and optional source URL; stores sha256, original filename, downloaded_at; moves the file to the store; text extracted, split into sections/passages, guidance parser run. Formats seen: PDF, DOCX, PPTX, HTML → text extraction needs new dependencies (e.g. pypdf, python-docx; `uv add` asks the owner).
- "I downloaded it" button: newest matching PDF/DOCX/PPTX in the Downloads folder (path from settings), name shown, ingest on confirm.
- Download checklist: when the nightly run sees an Item 2.02 8-K from a restricted-site spender, it queues `m02_ir_download` with the IR events page link and the expected documents; resolved when the file is ingested (or dismissed).
- Terms per site are recorded once (config, with the date checked) and drive auto-fetch vs inbox; re-check terms yearly.
- Grade B for third-party transcripts; A when the figure matches a company document or later filing (D-M02-6).
- Store whole in corpus.db as a company document type; same section/passage/FTS path; same guidance parser (expect new wording → review queue).
- One adapter (U7); record licence/terms in DATA_SOURCES.md.
