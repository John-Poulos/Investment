# Design-review packs (index)

Updated: 2026-10-12 · Research only — nothing in a pack is decided until the owner answers (D7). Answers become D-M0x-n decisions in the module's own doc (MODULE_TEMPLATE.md), recorded before the next round (design-review format).

## How a pack is used
- One design conversation per module, High effort; one round per section, in the pack's order.
- Each round: cited research → worked example → all cases → suggestions → failure modes → questions; answer in plain text ("1.1a 1.2b", "S2.4 no", "rest ok").
- Source IDs: S01–S121 from SOURCES.md; provisional "S-new-…" IDs are renumbered into SOURCES.md when a round is accepted.
- Each pack ends with proposed build parts (one conversation each at Medium effort, one live check each), known gaps and new sources.

## How the packs were made (2026-10-12, overnight)
- M04: six researchers (one per section), an adversarial source checker per section (111 problems fixed or removed), a synthesis, a completeness critique, and a section-by-section revision (153 critique points addressed; 77 points left as known gaps).
- M03, M05–M12: one researcher, one adversarial source checker (12–21 problems fixed or removed per module) and one pack writer per module.
- The owner's outline `docs/investment_strategy.txt` was added to the repo after the packs were written (the agents worked from DESIGN.md's module map and approved revisions). **Check each round against the outline's section for that module before asking its questions** — e.g. M07's Q3 ("CEO of equity", outline Ownership item 2) and M09's Q2 ("augmented trading range", outline Technical Analysis item 2) are quoted there.

## Packs
| Module | Pack | Rounds | Notes |
|---|---|---|---|
| M03 Leaders & S-curve | M03_DESIGN_PACK.md | segment data first, then S-curve types (R6), leadership | Needs M04 segment axes |
| M04 Financials & red flags | M04_DESIGN_PACK.md | data; earnings quality; dilution; survival gate; unit economics; CvD calibration | Largest pack (~400k characters); recommended first |
| M05 Capex & future spend | M05_DESIGN_PACK.md | builds on M02 money flow (D-M02-5, -28…33) | Coordinates A2 with M04 |
| M06 Moat | M06_DESIGN_PACK.md | moat evidence, duration (A3), challengers (R21) | Gates M11 |
| M07 Ownership & insiders | M07_DESIGN_PACK.md | Form 4 classification (R7, R13, R22), 13D/G, 13F | Prepares Q3 |
| M08 Sentiment & valuation | M08_DESIGN_PACK.md | valuation by stage (R6), revisions (R15), sentiment | Free estimate data is the main gap |
| M09 Technicals | M09_DESIGN_PACK.md | momentum/reversal by horizon (A4), R3, R17 | Prepares Q2 |
| M10 Macro & narrative | M10_DESIGN_PACK.md | FRED regimes, narrative, policy feeds (M02 7b) | No approved revisions yet |
| M11 Thesis, sizing & killswitch | M11_DESIGN_PACK.md | milestones (R4), ledger (R19), hurdle (R5), caps (R23), sizing | Depends on most modules |
| M12 Options overlay | M12_DESIGN_PACK.md | premium evidence, options data (Q5), IV history, window (R20) | One source URL in "New sources" was cut off |
