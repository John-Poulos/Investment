# M09 fixtures (Part 1)

Byte-exact (D24). Sources per file; everything else in `tests/test_technicals.py` is a
synthetic series built in the test itself (named there: steady trend, crash, partial week,
missing days, dividend refetch, split-adjusted closes, SPCX-length history, INFQ shell
cut-off, a symbol without a CIK).

- `mu_2022_23_anchors.json` — Micron's 2022–23 trough as daily anchors. Four anchors are
  stored Tiingo closes (equal to the pack's Yahoo closes, `docs/m04_review/PROBE_RESULTS.md`
  L9; values and dates from `docs/m04_review/R6_brief.md`): 48.88 on 2022-09-26 (the low),
  57.31 on 2022-10-07, 55.49 on 2022-12-22, 69.94 on 2023-10-06. The 2021-2022 maximum
  97.36 is a stored close whose date is not stated; it is placed on 2022-01-03 (synthetic
  placement). The 2021-09-01 start (80.00) is synthetic. Weekday closes between anchors are
  geometric interpolations (synthetic). The R6 brief's Q2 and Q3 FY23 closes (56.43, 69.09)
  are left out because their dates are not stated. Used for shape checks only (the low week
  below the band in a falling trend, the falling-knife label; the recovery week in an up
  trend), never as a known-answer test.

The pack's MU 2026, MSTR and SPY checkpoints (Yahoo weekly closes, `docs/M09_DESIGN_PACK.md`)
need full weekly series that the repo does not hold (Claude may not read `data\`); the
`signals` live check recomputes them from stored Tiingo bars and prints them beside the pack's
figures. Known-answer tests use closed forms instead (band_z = √19 when 19 equal closes are
followed by a higher one; pullback_sigma = −1 for alternating ±r returns ending at the base).
