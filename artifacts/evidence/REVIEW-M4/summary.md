# REVIEW-M4 evidence

Date: 2026-07-21. Task IDs M4-T1..T4.

## Code delivered
- `src/bearing_pdm/modeling.py` — naive baseline (mean training total-life minus elapsed, with a fitted per-bearing start-time reference) and `ExtraTreesRegressor` tree baseline (100 trees, seed 42, high-NaN columns excluded from candidacy).
- `src/bearing_pdm/evaluation.py` — `assert_no_leakage` guard (refuses to fit if `test_censored`/`full_test` rows are present), `leave_one_bearing_out_femto` (GroupKFold-style, whole bearings held out), `college_walk_forward` (chronological expanding-window, runtime-asserted).
- `scripts/evaluate_models.py`, `scripts/train_models.py` — CLI entry points (command.md section 20).
- `tests/test_modeling.py`, `tests/test_evaluation.py` — 22 tests, 70 total in the suite.

## One real bug found and fixed running against real data (docs/decisions.md D9)
The naive baseline's elapsed-time calculation was recomputed from whatever dataframe was passed to `predict()`. Correct by coincidence for FEMTO LOBO (a held-out bearing's test set is its whole trajectory, so its own start IS its true start) but wrong for college's later walk-forward folds, whose test slices start mid-run. Symptom: naive college MAE ballooned 108,038s (fold 1) -> 342,158s (fold 3) while extra_trees stayed flat (116,657 -> 131,762) - a broken reference, not a real model comparison. Fixed by storing each bearing's true start time at fit time and using it at predict time (falling back to the slice's own start only for a bearing genuinely unseen in training).

## One real finding, not a bug (docs/decisions.md D10)
After the fix, college's naive baseline scores **exactly 0.0 MAE on every fold** - not an error, a mathematical identity: college's `rul_seconds` label is itself `run_end_timestamp - event_timestamp` (the true final timestamp is known, since college is one uncensored run), and an expanding-window train fold always starts at true t=0, so the naive formula becomes algebraically identical to the label definition. This is documented as a property of the backtest setup, not a model capability - it must never be reported as "0 error."

## Final real-data results

### FEMTO leave-one-bearing-out (7534 rows, 6 bearings)
| model | mean MAE (s) |
|---|---|
| naive | 6584.8 |
| **extra_trees** | **5061.0** |

extra_trees beats naive on 4/6 held-out bearings (all by a wide margin on Bearing1_1, Bearing2_1, Bearing2_2, Bearing3_1); naive is marginally better on 2/6 (Bearing1_2, Bearing3_2 - both close). Full per-bearing table in `reports/metrics/rul_evaluation.json`.

### College walk-forward (4030-row 1-in-5 sample, single trajectory)
| model | MAE across 3 folds (s) |
|---|---|
| naive | 0.0 (not meaningful - see D10) |
| **extra_trees** | 116,657 / 118,904 / 131,762 (~33-37h on a ~128h run) |

extra_trees is the only real college RUL evidence; error grows slightly in later folds (harder, more nonlinear late-life dynamics with less training history), a reasonable and expected pattern.

## Frozen pipeline
`scripts/train_models.py` fit both models on all 7534 learning rows and saved `artifacts/models/rul_naive.joblib`, `rul_extra_trees.joblib`, and `rul_selected_model.json` (selects `extra_trees`, based on the LOBO mean MAE above - college's degenerate naive number is correctly excluded from the selection logic).

## M4 acceptance criteria (docs/milestone.md)
- Group/time splits only: yes - LOBO for FEMTO, chronological expanding-window for college; `assert_no_leakage` and a runtime chronology assertion enforce this.
- No preprocessing leakage: yes - median-fill values and feature selection are fit inside each fold/split, never on held-out data.
- Per-bearing metrics: yes, full table in `reports/metrics/rul_evaluation.json`.
- Frozen final pipeline: yes, saved before any `Full_Test_Set` scoring (which hasn't happened - out of scope until a dedicated hidden-set evaluation step, deferred).

## Verdict
M4 gate met. Proceeding to minimal M8 (Streamlit dashboard).
