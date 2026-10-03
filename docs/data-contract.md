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

## Incremental headered CSV feature windows

`bearing_pdm.chunked.iter_csv_window_features` is a standalone library iterator,
not an upload endpoint or a dataset compatibility decision. Callers supply the
vibration column, positive integer window length and chunk size, integer overlap
in `[0, window_samples)`, and a known finite positive sampling rate. There is no
assumed sensor unit or sampling rate and no model invocation.

Each `WindowFeatures` record contains zero-based `row_start`, exclusive
`row_stop`, and the existing time-domain and FFT feature dictionary for that
complete window. The stride is `window_samples - overlap_samples`. CSV chunk
boundaries never define scientific windows. Only the selected column is loaded,
with a fixed float64 dtype. Missing samples and blank rows retain their positions;
features.py's existing within-window NaN omission and all-missing NaN outputs
apply unchanged. In particular, its documented FFT spacing limitation on missing
samples still applies. There is no global imputation or padding.

Pass a fresh `WindowReport` and exhaust the iterator to obtain `completed=True`,
rows read, windows emitted, trailing partial rows, and peak rows held. The trailing
count is the length of the incomplete window at the next stride position, so it
includes retained overlap even if those samples appeared in the last full window.
A file shorter than one window emits nothing and reports its entire length as
partial; a header-only file reports zero. Invalid numeric data or a missing column
raises an error; a failed or abandoned stream is not marked completed. Consumers
must discard partial results on failure and close an iterator abandoned early.

The retained input storage is one pandas chunk plus one preallocated window;
`peak_rows_held` counts these row slots, bounded by `chunk_rows + window_samples`.
This is not a process RSS measurement: pandas parser buffers, temporary arrays
inside the unchanged feature formulas, and feature records retained by a caller
are excluded. Consume records incrementally to avoid accumulating output in RAM.

`bearing_pdm.chunked.scan_csv_column` is the matching validation pass: it reads the
same column with the same header/blank-row handling, one chunk at a time, and
returns counts only (rows, missing, non-numeric, infinite, finite min/max, and
optionally rows where a numeric order column is not strictly increasing). Values
are never retained. `POST /analyze/features` (`docs/feature-analysis.md`) runs it
before the iterator so the window count is known and data problems are attributed
to validation rather than to feature extraction.
