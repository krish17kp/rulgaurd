# Prediction reliability (`POST /predict/rul`)

`/predict/rul` returns a `reliability` block next to the unchanged fields (`model_name`,
`rul_seconds`, `rul_hours`, `features_used`, `features_missing`). It is built in
`src/bearing_pdm/reliability.py`, only from assets the project already produces. The API fits
nothing, and every number comes from a file or from a computation on the request row.

**No field is a confidence score, a probability or a percentage.** Tests enforce this
(`tests/test_reliability.py`): no key may contain `confidence`, `probability`, `percent` or `pct`.
The one stored rate in the metrics file, `overestimate_rate`, is left out on purpose; the
signed mean error says which way the model tends to be wrong.

When a part cannot be produced, that part is withheld and a reason is given. It is never guessed
or filled with a default.

| Part | Source | Unit | When unavailable |
| --- | --- | --- | --- |
| `held_out_error` | `reports/metrics/rul_evaluation.json` (`scripts/evaluate_models.py`) | seconds | `available: false` + `reason` (file absent, or no complete finite `extra_trees` results) |
| `tree_disagreement` | `uncertainty.tree_predictions` on the served model, for this row | seconds | `available: false` + `reason` (the model exposes no trees) |
| `interval` | cached calibrator `cross_domain_bundle.joblib["raw_seconds"]["calibrators"]["conformal"]` + `uncertainty.conformal_interval` | seconds (and hours) | `null` + `interval_reason` |
| `applicability` | cached `cross_domain_bundle.joblib["raw_seconds"]["applicability"]` + `applicability.assess` | `shift_ratio` is dimensionless | `null` + `applicability_reason` |

## held_out_error

These are the FEMTO leave-one-bearing-out results for `extra_trees`:

- Pooled over every held-out row: `mae_seconds`, `rmse_seconds`, `median_abs_error_seconds`
  and `mean_signed_error_seconds` (positive means RUL was over-estimated), with `n_held_out_rows`.
- The spread across folds: each held-out bearing's own MAE and `n` in `per_bearing`, plus
  `per_bearing_mae_seconds_min/max`.

This measures the training procedure on bearings it did not see. It is not an error bound for
this one prediction. When the file is missing (as it is in a checkout without
`scripts/evaluate_models.py` output), the block says so and reports no statistics.

## tree_disagreement

`std_seconds` is the standard deviation of the ExtraTrees' per-tree predictions for this row,
with `n_trees`. It is labelled `kind: diagnostic_not_calibrated`. Every tree was fit on the
same training bearings, so the trees can agree with each other and still all be wrong
(`uncertainty.py`).

## interval

This is a normalised split-conformal interval, `prediction ± q·(σ + β)`, with the lower bound
clipped at 0 s. `q` and `β` come from the calibrator that `scripts/run_cross_dataset.py` fit
offline, using out-of-fold predictions on the FEMTO learning bearings (`experiments.calibrate`).
σ is the tree disagreement above. The response carries the calibrator's
`target_miscoverage_alpha` (0.1), `n_calibration_bearings` and `n_calibration_rows`.

The interval is reported only when all of these hold. Otherwise it is `null` with the reason:

1. the bundle exists and its `raw_seconds` entry was trained on `femto` (D11);
2. the bundled model has the served model's feature schema **and** reproduces the served
   prediction for this row, so the calibrator belongs to the served model and not to an
   older or newer one;
3. tree disagreement is available (the calibrator scales by it);
4. applicability was computed and is `HIGH`. The coverage target assumes the row is
   exchangeable with the FEMTO calibration bearings. A `LOW` row never gets this far (its
   prediction is suppressed with 422 `APPLICABILITY_LOW`, `docs/dataset-compatibility.md`), and
   a `MEDIUM` row is served as an experimental result (`compatibility: RETRAIN_REQUIRED`), which
   is not evidence of exchangeability either.

`alpha` is a property of the method. It is the long-run miscoverage it targets across
exchangeable bearings, and with 6 calibration bearings that target is coarse. It is not a
probability that this prediction is right. `docs/cross-dataset-results.md` reports the coverage
actually measured for `raw_seconds` normalised conformal. It is 1.000 on the FEMTO hidden set
and on FEMTO leave-one-bearing-out, but 0.341 zero-shot on college. That is why FEMTO-only
gating (D11) and the applicability check come first.

## applicability

`applicability.assess` treats the submitted row as a single recording
(`single_recording=True`, the same call and level as the prediction's own applicability gate
and the response's top-level `applicability_level`, so one response never reports two levels).
It returns `level` (HIGH/MEDIUM/LOW), `shift_ratio`, the distances it is computed from,
`reasons` and `missing_features`. A feature that was not submitted counts as unavailable. It is
**not** counted as its training median, even though the point prediction median-fills it. The
missing-feature cap uses the fraction of the row's features that are missing: more than half
is `LOW` (suppressed), more than 10% is at most `MEDIUM`; either way there is no interval.

`checks_not_performed` lists what this request cannot support: operating metadata (sampling
rate, speed, load) and the life time-scale check (elapsed time). Neither is part of the request.

## Known limitations

- The applicability reference rows include the FEMTO training bearings. A row taken from one of
  those bearings will look in-domain trivially, because the API cannot tell which bearing a row
  came from (compare `applicability.exclude_bearing`, used offline).
- The bundle is about 200 MB and is loaded once per process on the first prediction. If it is
  not deployed (for example on a size-limited host), `interval` and `applicability` are `null`
  with a reason, and the prediction itself is unaffected.
- If an unexpected error happens while the block is being built, every part is withheld with a
  generic reason. The prediction is still returned, and the log records only the exception
  type.

`POST /analyze/rul` reuses this same reliability block for the last complete raw acquisition,
after its domain, units, preprocessing and schema checks. It does not create an additional
confidence score. See [raw acquisition analysis](feature-analysis.md#raw-acquisition-prediction-post-analyzerul)
for the request contract and fail-closed outcomes.
