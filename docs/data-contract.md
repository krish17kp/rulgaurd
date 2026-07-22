# Data Contract (canonical feature-row schema, version `v1`)

Every adapter (`femto.py`, `college.py`) emits rows matching this contract before anything touches modeling code.

## Identifiers & lineage
| field | type | notes |
|---|---|---|
| `acquisition_id` | str (uuid) | matches `acquisitions.acquisition_id` |
| `dataset_id` | str | `'femto'` \| `'college'` |
| `bearing_run_id` | str | `'femto:Bearing1_1'` etc. |
| `role` | str | `'learning'` \| `'test_censored'` \| `'full_test'` \| `'college_run'` |
| `source_file_path` | str | relative to configured raw dir |
| `sequence_index` | int | acquisition index (FEMTO) or window index (college) |
| `event_timestamp` | datetime | parsed, not assumed monotonic-without-check |
| `sample_rate_hz` | float | 25600.0 for both datasets |
| `n_samples` | int | 2560 (FEMTO) or 25600 (college default) |
| `schema_version` | str | `'v1'` |
| `source_sha256` | str | hash of the source file (or chunk range for college) |

## Signals
| field | type | notes |
|---|---|---|
| `temp_available` | bool | false when no temperature file/column exists |
| vibration/temperature raw arrays | not stored in the contract | features only - see `docs/architecture.md` |

## Targets
| field | type | notes |
|---|---|---|
| `rul_seconds` | float, nullable | FEMTO: `final_acquisition_time - current_time`; college: `final_file_time - current_window_time`. NULL for `full_test` role until frozen-model evaluation. |
| `stage_label` | str, nullable | policy documented at construction time; NULL if not yet labeled |

## Dataset-specific mappings
- **FEMTO**: one row per 2560-sample acceleration acquisition file (`acc_NNNNN.csv`). Temperature aligned by nearest acquisition within a documented tolerance (default: same 10-second cycle index) when `temp_NNNNN.csv` exists for that index.
- **College**: one row per 25,600-sample / 50%-overlap window inside each hourly file. Window carries `row_start`/`row_end` into the source CSV. Final incomplete window per file: dropped by default (config flag `keep_incomplete_window`, default `false`), because the trailing runt window offers no additional shaft revolutions worth featurizing (`ponytail:` this is a threshold call - revisit if a review question needs full-file coverage).

## Missing-temperature rules
`temp_available=false` propagates to every temperature-derived feature (set NaN, never 0 or forward-filled). No global imputation across files.

## Train/test role and leakage guards
- FEMTO fitting (scalers, PCA, HI orientation, model hyperparameters) uses `role='learning'` rows only.
- `role='test_censored'` rows may be scored once the pipeline is frozen.
- `role='full_test'` rows are for final RUL derivation only, never for fitting - enforced by a runtime assertion in `evaluation.py` before any `.fit()` call touches them (M4).
- College: time-ordered split only; a runtime assertion rejects any train/test split for the college run that isn't strictly chronological.

## Schema version
`v1` as defined above. Any breaking change bumps to `v2` and the DuckDB `feature_batches.schema_version` records which version produced each Parquet file.
