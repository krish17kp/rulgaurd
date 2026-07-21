# REVIEW-M3 evidence

Date: 2026-07-21. Task IDs M3-T1, M3-T2.

## Code delivered
- `src/bearing_pdm/health.py` — transparent baseline HI (z-score of RMS+kurtosis vs a training-derived healthy baseline, squashed to (0,1]) and paper-inspired PCA HI (monotonicity x trendability feature ranking -> StandardScaler -> PCA(1) -> life-fraction-oriented -> min-max to [0,1]). Both fit only on `role='learning'` rows.
- `scripts/build_health.py` — CLI: loads the latest FEMTO learning Parquet batch from DuckDB, fits + evaluates both HIs, writes metrics JSON, two plots, and joblib-serialized fitted models.
- `tests/test_health.py` — 14 tests on synthetic degrading data (real formulas, deterministic synthetic input for speed/determinism).

## Two real bugs found and fixed running against real data (docs/decisions.md D7, D8)
1. **D7**: PCA HI's feature selection picked temperature columns that are 100%-missing for 2 of 6 learning bearings (zero temp files, confirmed in M1), then `fillna(median)` fabricated a full signal for them — violating the project's own no-fabrication rule. Fixed: `candidate_feature_columns(max_nan_fraction=0.2)` excludes structurally-sparse columns from PCA candidacy entirely, before any imputation.
2. **D8**: PCA HI's orientation sign was computed from pooled raw `sequence_index` across bearings of very different lengths (515-2803), which inverted the sign for **all 6 bearings** (trend_corr was positive everywhere — HI rising as bearings degraded). Fixed to use per-bearing life-fraction, matching normalization already used correctly elsewhere in the file. After the fix, all 6 bearings show negative trend_corr.

## Final real-data results (FEMTO learning set, 7534 rows, 6 bearings — reports/metrics/health_indicator_comparison.json)

| HI | mean monotonicity | mean trend_corr |
|---|---|---|
| Transparent (RMS+kurtosis z-score) | 0.0087 | **-0.5255** |
| PCA (8 selected features) | 0.0193 | -0.4648 |

**Selected: transparent_hi** (higher \|mean trend correlation\|). Per-bearing trend_corr for transparent HI ranges from -0.14 (Bearing1_2, weak) to -0.87 (Bearing1_1, strong) — all correctly signed (HI falls as the bearing degrades), no bearing inverted.

`reports/figures/hi_transparent.png` shows a real, physically sensible pattern: Bearing1_1 (the longest run, 2803 acquisitions) has a clean, near-monotonic decline from ~1.0 to ~0.03 over its life. Shorter bearings show more early-life instability (a documented, expected "break-in" pattern in bearing degradation literature) before their final decline.

## Known limitation, documented not hidden
Per-acquisition monotonicity is low for both HIs (0.009-0.02, far from 1.0). This is because monotonicity is measured at the native per-acquisition (every 10s) granularity, which is inherently noisy — the trend_corr metric (which captures the overall direction, not sample-to-sample noise) is the more meaningful signal here and is what the selection is based on. A smoothed/rolling HI would likely improve monotonicity; out of scope for the M3 baseline, flagged as a natural M4/M8 refinement if the RUL model needs it.

## M3 acceptance criteria (docs/milestone.md)
- Train-only fitting: yes — both HIs calibrated only on `role='learning'` rows; `test_censored`/`full_test` never touched.
- Monotonicity/trend evidence: yes, both metrics computed and reported per bearing, real numbers, no fabricated results.
- No hidden-test use: yes — only the FEMTO learning Parquet batch was used.
- One baseline selected or rejection documented: yes — transparent HI selected by trend_corr; PCA HI's weaker result and its two real methodology bugs are documented, not hidden.

## Verdict
M3 gate met. Proceeding to M4 (RUL baselines).
