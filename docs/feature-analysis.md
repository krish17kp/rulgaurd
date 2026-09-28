# Staged feature analysis: `POST /analyze/features`

The first half of the Goal 26 pipeline: **Upload -> Dataset Detection -> Validation ->
Preprocessing -> Feature Extraction**. It returns per-window signal features and an explicit
`stages` array. It computes **no health indicator, stage or RUL and loads no model**, so the
FEMTO-only model gate (`docs/decisions.md` D11) is never involved and no cached model is
applied to the uploaded data.

## Request

Multipart `file` (one headered, comma-separated UTF-8 file) plus query parameters:

| Parameter | Required | Meaning |
|---|---|---|
| `channel` | yes | The vibration header column, or the canonical name (`vibration_x/y/z`) that exactly one high-confidence header maps to. |
| `sampling_rate_hz` | unless derivable | Acquisition rate. Without it, the rate is taken only from a regular timestamp column in seconds (`profiler.sampling_info`); otherwise the request fails. Never guessed from an adapter or dataset name. |
| `window_samples` | no (default 2560) | Window length in samples. 2560 is the FEMTO acquisition length (0.1 s at 25.6 kHz); it is only a default and says nothing about other machines. The response reports the window length in seconds at the stated rate. |
| `overlap_samples` | no (default 0) | Must be smaller than `window_samples`. |

## Stages

Every stage starts as `skipped`; each is set exactly once to `ok` or `failed`. A failure
stops the pipeline, so all earlier stages are `ok`, the failed stage is `failed`, and later
ones stay `skipped`. The same array is returned on success and in every staged error body
(with `failed_stage`), and the access log records `pipeline_stage` (`docs/observability.md`).

| Stage | Reuses | Fails with |
|---|---|---|
| `upload` | the `/dataset/inspect` spool (64MB limit, text-head check, temp file) | `EMPTY_UPLOAD`, `UPLOAD_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`, `UNDECODABLE_FILE`, `MALFORMED_FILE`, `STORAGE_UNAVAILABLE` |
| `dataset_detection` | `profile_file`, `sampling_info`, `_classify_detailed` | `MALFORMED_FILE` (unreadable), `ADAPTER_REQUIRED` (no header / low-confidence vibration name), `NO_VIBRATION_CHANNEL`, `UNSUPPORTED_DELIMITER` (multi-column file that is not comma-separated), `CHANNEL_NOT_FOUND`, `CHANNEL_AMBIGUOUS`, `CHANNEL_NOT_VIBRATION` |
| `validation` | `chunked.scan_csv_column` (whole file, chunked) | `INVALID_WINDOW`, `TIMESTAMPS_IRREGULAR`, `SAMPLING_RATE_CONFLICT` (user rate differs >1% from timestamps), `SAMPLING_RATE_REQUIRED`, `INSUFFICIENT_SAMPLES` (fewer samples than one window), `NON_NUMERIC_SIGNAL`, `NON_FINITE_SIGNAL`, `CONSTANT_SIGNAL`, `EXCESSIVE_MISSING` (> `routing.MAX_NAN_FRACTION`), `SAMPLES_OUT_OF_ORDER` (numeric timestamp column not strictly increasing) |
| `preprocessing` | - | Framing only; cannot fail. |
| `feature_extraction` | `chunked.iter_csv_window_features` | `FEATURE_EXTRACTION_FAILED`, `MEMORY_LIMIT_EXCEEDED` |

Validation collects every problem it finds: `code` is the first, `validation_errors` lists all.
Detection's structural `compatibility` (column mapping) is reported, but data quality of the
chosen channel is decided by validation's whole-file scan, not by the profiler's 5000-row
sample; `INVALID_INPUT` from the sampled check is therefore reported, not used as the verdict.
Reasons contain counts and column names only, never cell values.

**Preprocessing** is deliberately minimal: fixed-length windows at the given stride. There is
no filtering, detrending, resampling, padding or imputation. Missing samples are omitted inside
each window by the `features.py` formulas (their documented NaN policy); trailing samples that
do not fill a window are reported and not used.

## Response

`windows` holds at most `MAX_RETURNED_WINDOWS` (200) windows, in source order, each with
zero-based `row_start` (inclusive) / `row_stop` (exclusive) data-row offsets (header excluded)
and the 14 time-domain plus frequency-domain features from `features.py`, prefixed by the
header column name. `windows_total` is exact (computed from the validated sample count);
when it is larger, `truncated` is `true`, `truncation_note` says so, and later windows are
not computed. Non-finite feature values (e.g. kurtosis of a flat window) are returned as
`null` and counted in `non_finite_feature_values`.

`health_indicator_produced` and `prediction_produced` are always `false`. Amplitude features
are in the channel's recorded units, which this endpoint does not determine.

## Limitations

- One comma-separated, headered file and one channel per request; headerless files (e.g. the
  raw FEMTO/college fixtures) need an adapter and fail at detection.
- The file is read three times (profile, scan, extraction), each bounded in memory; the raw
  upload is kept only in a temporary file that is deleted when the request ends.
- A numeric timestamp column in unknown units is checked for ordering only; it does not
  supply a sampling rate.
