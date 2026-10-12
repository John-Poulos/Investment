# Lessons that generalize (running)

Updated: 2026-10-12 · Read at the start of every module build. One line each, with the decision that holds the detail. Add a lesson when a mistake or surprise in one module would recur in another.

## Data sources
- Count what you mean: EDGAR full-text search counts documents, not filings; a filing whose exhibits match counts twice. Report distinct filings and companies (D-SEC-14).
- A checkbox on a form is not a flag on each row (Form 4 10b5-1 box is per form; per-row evidence comes from footnotes) (D-SEC-10).
- Calendar-quarter XBRL frames are sparse for Q4 (reported inside the annual figure); use each company's own series for TTM and YoY (D-SEC-9).
- Same fiscal period can be reported with start dates a day apart; dedupe on (type, end) and name the alternative (D-SEC-17).
- Market dates are US Eastern; an evening run in UTC is already "tomorrow" (D-SEC-16).
- A bare 403 from SEC Archives can mean "not published yet", not a block (D-SEC-16).
- EFTS through the API: `entity_filter` lists only the top 30 filers; `NEAR(n)` returns nothing; some quoted phrases get a persistent 5xx on a long window — retry as two halves before calling it missing (D-M02-17).
- SEC companyfacts carries standard taxonomies only; company extension tags (e.g. `amzn:`) need the filing's XBRL instance (`<primary>_htm.xml`) — fetch it only where a recipe or coverage check needs it (D-M02-32).
- A ratio of mapped lines to a net total swings when the net is small; measure coverage against gross flows plus the unexplained residual (D-M02-33).
- A share needs a denominator from the same source family and window: EDGAR's quarterly form index gives exact distinct filers per form (D-M02-17).
- 13F values are thousands of dollars in filings made before 2023-01-03 and dollars after — scale by filing date; one issuer can span several rows (other managers), so sum by CUSIP before comparing quarters (D-M02-45, D-M02-46).
- A company's submissions list mixes filings it made with filings about it (funds' 13Gs); only the index header says who filed — read it once and keep the answer (D-M02-45).
- When the counterparty of a disclosure has no stored documents, stored-text finders find nothing; search the counterparty's filings with targeted phrases instead (D-M02-45 (4)).
- Seed phrases need the same scrutiny as mined ones: a generic phrase ("domestic manufacturing") can dominate a theme (D-M02-17).
- A year-over-year comparison inside a stored corpus measures what was stored, not what changed: 220 documents vs 32 made "inline xbrl" and "cash flow" rise; compare each company with its own documents of the same kind a year earlier (D-M02-52).
- New accounting standards and tax laws make every filer adopt the same wording in the same year; a "new phrase" miner must read narrative sections (business, risk factors, MD&A), not financial-statement notes, and drop accounting/tax/legal words (D-M02-54).
- A section label match must be exact and form-specific: "Item 1" is the business in a 10-K but the financial statements in a 10-Q (D-M02-54).
- Calibrate a cut-off on known cases before enforcing it: 50% / 75% industry concentration would have rejected 12 of 36 real seed themes, because value chains span related industries and finance filers mention themes as holdings or risks (D-M02-52).

## Rate limits and budgets
- Sustained bulk near a published limit gets blocked: SEC blocked at 7.5–8/s against a 10/s limit; we pace at 5/s (D-SEC-18).
- Check the shared fetch log before each request so all processes stay under one budget (Tiingo, D-UI-8); the SEC limiter is still per process (M00_SEC_DATA open item).
- A budget stop ends the batch and leaves the rest for the next run; it is reported, never silent (D-UI-8).
- Count limits need counting, not spacing: pacing Tiingo at 75–90 s made a 17-symbol run take 20+ minutes while the hourly count check already guarded the limit (D-UI-19).
- For discovery passes the owner's review queue, not SEC time, is the binding constraint: rank before queuing, cap per pass, flush in the approved priority order (D-M02-51).
- A scheduled task killed at its time limit or at shutdown skips cleanup (TerminateProcess): locks need a stale check, every SEC-calling script must take the lock, and no modal box may wait while the lock is held (D-M02-51).
- "Nightly" jobs run at logon during the owner's session (PC off overnight): keep them in the background, keep write transactions short (the app writes too; busy_timeout 5 s), stay well inside the 3-h task limit, and leave part of any shared API budget for interactive use (D-M02-12).

## Parsing and numbers
- Exact binomial tails overflow a float once counts reach the thousands (EFTS document totals); compute in log space (D-M02-53).
- Ratios on a near-zero base (tax rate 476%) are transcribed correctly but meaningless; flag `not_meaningful`, keep, exclude from scoring and LLM input (D-SRCH-15).
- Table cells must stay separated (tabs) in stored text or parsers read the wrong column (D-SRCH-12, D-UI-10).
- Reported actuals and guidance share sentences; the forward verb must precede each value (D-SRCH-12).
- Company period labels are kept as stated (fiscal vs calendar) and mapped to dates only when scoring (M00_SEARCH failure modes).
- Probe a vendor's period parameter with an off-calendar company (Microsoft June FY, Oracle May FY) before building: Alpha Vantage's `quarter` is the company's fiscal label (D-M02-6).
- Call transcripts mix analyst questions with management statements; parse management turns only, or analysts' numbers become "guidance" (D-M02-6).
- An empty vendor response is "not available yet", never "none" (Alpha Vantage returned an empty transcript for a month-old call) (D-M02-6).
- Run the parser on the real corpus early; each live scan found new wording (guidance-1 → guidance-4).
- A vendor document may carry no date (Alpha Vantage transcripts): anchor it to an SEC record (the quarter's earnings 8-K) and leave it unparsed when none matches, rather than using the fetch date (D-M02-22).
- Spoken periods are relative ("next quarter", "this year"); resolve them only against the document's own fiscal quarter, and leave the ambiguous ones ("this year" on a Q4 call) for review (D-M02-22).
- Spoken guidance retells old figures ("earlier this year we said …"), quotes other companies' numbers ("hyperscaler capex"), names segments ("AI revenue") and states bounds ("more than $25 billion"); a release parser applied to calls takes all of these as guidance (D-M02-23).
- Sanity bounds must compare with the latest period, not a year-old average: fast growers otherwise flood the queue (D-M02-25).
- When a parser yields nothing for a company that should have data (Alphabet's call capex), log the sentences that mention the target with a figure and why each was set aside, before guessing at rules (D-M02-25).
- An 8-K item code is not one event type: Tesla's deliveries report and its results both carry Item 2.02; pick the filing by timing, not by item alone (D-M02-23).
- Mark non-SEC documents in their identifier (accession prefix `AV-`, `IR-`) so every view — reader, search, ledger, Gemini citations — can label the source without a join (D-M02-22).

## LLM
- Measure an LLM labeller against the owner's blind labels before its output feeds anything; show it as a hint, keep the owner's confirmation (D-M02-9, D-M02-40: precision 82%, direction 77%).
- Check model names against the provider's docs before coding ("Gemini 3.1 Flash" did not exist) (D-SRCH-16).
- Verify every quote and every number mechanically; reject, store the rejection, queue it (D-SRCH-19).
- Cache identical requests; show the prompt, tokens and cost before any call (D-SRCH-19, D-UI-11).
- Do not send boilerplate passages (forward-looking-statement text) as context (D-SRCH-20).
- Say "no reason stated" rather than inventing one; the first live run did this correctly (D-SRCH-20).

## UI
- Jinja resolves `row.items` to the dict method; read clashing keys with `row['key']`; a test fails if any tab renders a Python object (D-UI-7). Hit again in part 4 (`call_document` + `guidance_scan.items`): name SQL columns `n_items` or read with `[]`.
- Show basis or labels only when the source stated them; store `unspecified` (D-SRCH-20).
- Review policy: real information the program cannot store yet stays open for its future module (D-UI-15).
- Never re-case names ("NVIDIA CORP" → "Nvidia Corp" by title-casing): show the SEC registry name when resolved, else the name as the filing states it (D-M02-46).

## Process
- A store of code-found passages needs a re-read path from day one: rules change after every live log; keep first-seen dates and never delete an answer key (D-M02-37, D-M02-40).
- Company names in filing text: competitor lists, share sales and product names look like relationships; filter them and let the owner confirm each link (D-M02-37…40).
- Mock up each screen with real stored data before building it (D-UI-4).
- Regex and `\n` edits through shell (sed, heredoc Python) lose their backslashes — hit twice more in part 5b; use the Edit tool for any string with a backslash.
- Windows PowerShell 5.1 `Set-Content -Encoding utf8` adds a BOM and mangles non-ASCII read through the console code page (part 6, twice); edit with the Edit tool or a Python script file, never PowerShell text cmdlets.
- A scheduled job's lock needs an owner and a heartbeat, not an age: a task killed at its limit leaves the file behind (D-M02-51, -53).
- Owner runs live tests and sends a short log; keep live output to summaries (context cost).
