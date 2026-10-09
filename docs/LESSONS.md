# Lessons that generalize (running)

Updated: 2026-10-09 · Read at the start of every module build. One line each, with the decision that holds the detail. Add a lesson when a mistake or surprise in one module would recur in another.

## Data sources
- Count what you mean: EDGAR full-text search counts documents, not filings; a filing whose exhibits match counts twice. Report distinct filings and companies (D-SEC-14).
- A checkbox on a form is not a flag on each row (Form 4 10b5-1 box is per form; per-row evidence comes from footnotes) (D-SEC-10).
- Calendar-quarter XBRL frames are sparse for Q4 (reported inside the annual figure); use each company's own series for TTM and YoY (D-SEC-9).
- Same fiscal period can be reported with start dates a day apart; dedupe on (type, end) and name the alternative (D-SEC-17).
- Market dates are US Eastern; an evening run in UTC is already "tomorrow" (D-SEC-16).
- A bare 403 from SEC Archives can mean "not published yet", not a block (D-SEC-16).

## Rate limits and budgets
- Sustained bulk near a published limit gets blocked: SEC blocked at 7.5–8/s against a 10/s limit; we pace at 5/s (D-SEC-18).
- Check the shared fetch log before each request so all processes stay under one budget (Tiingo, D-UI-8); the SEC limiter is still per process (M00_SEC_DATA open item).
- A budget stop ends the batch and leaves the rest for the next run; it is reported, never silent (D-UI-8).
- "Nightly" jobs run at logon during the owner's session (PC off overnight): keep them in the background, keep write transactions short (the app writes too; busy_timeout 5 s), stay well inside the 3-h task limit, and leave part of any shared API budget for interactive use (D-M02-12).

## Parsing and numbers
- Ratios on a near-zero base (tax rate 476%) are transcribed correctly but meaningless; flag `not_meaningful`, keep, exclude from scoring and LLM input (D-SRCH-15).
- Table cells must stay separated (tabs) in stored text or parsers read the wrong column (D-SRCH-12, D-UI-10).
- Reported actuals and guidance share sentences; the forward verb must precede each value (D-SRCH-12).
- Company period labels are kept as stated (fiscal vs calendar) and mapped to dates only when scoring (M00_SEARCH failure modes).
- Probe a vendor's period parameter with an off-calendar company (Microsoft June FY, Oracle May FY) before building: Alpha Vantage's `quarter` is the company's fiscal label (D-M02-6).
- Call transcripts mix analyst questions with management statements; parse management turns only, or analysts' numbers become "guidance" (D-M02-6).
- An empty vendor response is "not available yet", never "none" (Alpha Vantage returned an empty transcript for a month-old call) (D-M02-6).
- Run the parser on the real corpus early; each live scan found new wording (guidance-1 → guidance-4).

## LLM
- Check model names against the provider's docs before coding ("Gemini 3.1 Flash" did not exist) (D-SRCH-16).
- Verify every quote and every number mechanically; reject, store the rejection, queue it (D-SRCH-19).
- Cache identical requests; show the prompt, tokens and cost before any call (D-SRCH-19, D-UI-11).
- Do not send boilerplate passages (forward-looking-statement text) as context (D-SRCH-20).
- Say "no reason stated" rather than inventing one; the first live run did this correctly (D-SRCH-20).

## UI
- Jinja resolves `row.items` to the dict method; read clashing keys with `row['key']`; a test fails if any tab renders a Python object (D-UI-7).
- Show basis or labels only when the source stated them; store `unspecified` (D-SRCH-20).
- Review policy: real information the program cannot store yet stays open for its future module (D-UI-15).

## Process
- Mock up each screen with real stored data before building it (D-UI-4).
- Owner runs live tests and sends a short log; keep live output to summaries (context cost).
