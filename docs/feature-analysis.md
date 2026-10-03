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

## Raw acquisition prediction: `POST /analyze/rul`

This endpoint extends the same upload, detection, validation, framing and feature extraction
code to both canonical vibration axes, then calls `/models/compatibility`, `/predict/hi`
and `/predict/rul` internally. It never fits a model. `/analyze/features` remains unchanged.

Send one headered CSV containing `vibration_x` and `vibration_y` (or unambiguous,
high-confidence header aliases). Each consecutive block of 2560 rows must be one complete
FEMTO acquisition, in acquisition order, from the same bearing. Headerless source files must
be exported with the adapter's two acceleration column names; acquisition timestamp columns
are not sample timestamps and should not be relabelled as such.

Required query parameters are `dataset_id`, `units` and `preprocessing_version`.
The only accepted prediction contract is `dataset_id=femto`, `units=g`,
`preprocessing_version=femto-acquisition-v1`. Supply `sampling_rate_hz=25600` unless regular
sample timestamps in seconds establish that rate. Optional `window_samples` and
`overlap_samples` must be 2560 and 0 respectively. Other domains receive the existing
compatibility outcome (`RETRAIN_REQUIRED` or `UNSUPPORTED`) and no prediction, even if their
feature names match (D11).

`femto-acquisition-v1` is a **code-owned serving contract** for the legacy FEMTO artifacts,
which do not embed units or preprocessing metadata. It means the original acceleration in g,
complete 2560-sample acquisitions at 25.6 kHz, and the existing `features.py` formulas, with
no filtering, resampling, scaling, overlapping windows or prior signal transforms. It does
not claim artifact-embedded provenance. The existing selected-model allowlist binds this
contract to the cached ExtraTrees path; introducing another model requires a separately
validated serving contract. Model version and feature schema version are the existing
content/schema fingerprints, returned in `model` alongside the training domain.

Dataset identity, units and acquisition ordering are caller declarations. CSV shape cannot
prove machine provenance, healthy initial conditions or whether an upstream transform was
applied. Do not label an arbitrary CSV as FEMTO to bypass D11. No support for arbitrary
machines is implied by a `FULLY_SUPPORTED` metadata outcome.

The response adds `model_compatibility`, `health_indicator` and `prediction` to `stages`.
It returns the **last complete acquisition's** `rul_seconds` and `rul_hours`, `model`,
`compatibility`, `preprocessing_version`, `warnings`, and the unchanged
[reliability block](prediction-reliability.md). `supporting` contains that acquisition's
canonical derived features, zero-based sequence index, acquisition count, units, window,
sampling provenance and HI model version. Raw samples are not returned or logged.

The metadata gate cannot see feature values, so the `prediction` stage also carries
`/predict/rul`'s applicability check on the latest acquisition (`applicability_level`,
`applicability_shift_ratio`, `applicability_reasons` in the response): LOW suppresses the RUL
(422 `APPLICABILITY_LOW`, `failed_stage: prediction`, `compatibility: RETRAIN_REQUIRED`), and
MEDIUM returns it with `compatibility: RETRAIN_REQUIRED` and the experimental caveat added to
`warnings` — never `FULLY_SUPPORTED`. The request produces one prediction-history record,
kind `analyze_rul` (`docs/prediction-history.md`).

`health` contains the existing `/predict/hi` response, including per-recording severity
stages and thresholds. HI is not an input to the cached RUL regressor. For fewer recordings
than its reference window requires, HI alone is withheld (`health=null`,
`health_indicator_produced=false`, the health stage is `skipped`, and an explicit warning).
The independently supported RUL is still returned. This preserves the existing independent
prediction contracts; it does not fabricate a healthy baseline or a severity stage. With a
long enough history, every `/predict/hi` validation applies, including its degenerate-reference
check; a failure suppresses the whole result. Its reference window must represent the actual
beginning of the run, with the healthy-baseline assumption described by that endpoint.

Failures use **HTTP 4xx/5xx**, never HTTP 200 prediction success. Staged failures contain the
error code, explanation, failed stage, stages array, `prediction_produced=false` and null
`rul_seconds` / `rul_hours`. Framework query validation errors retain the standard 422 error
contract and contain no prediction. Missing selected-model metadata, RUL or HI artifacts
produce 503 `MODEL_UNAVAILABLE`. Clients must require HTTP success and
`prediction_produced=true` before showing a RUL; health availability is separate.

Additional fail-closed checks reject incompatible units/preprocessing, any absent model
feature, non-finite derived values, trailing partial acquisitions, and runs exceeding the
200-window response limit. Unlike feature-only inspection, prediction never silently drops
samples or reports a capped prefix as the latest acquisition. Both channels undergo the
same full-file validation; failures in the second channel leave downstream stages skipped.

Tests compare the real FEMTO fixture's raw CSV result against `/predict/rul` for independently
extracted features with numerical tolerances. HI orchestration is compared with `/predict/hi`
on an explicitly artificial history composed of the two fixture acquisitions. These are
numerical integration checks, not held-out predictive performance evidence.

## Deployment/offline parity regression (Goal 35)

`tests/test_parity.py` exercises the Vercel ASGI `/api` mount locally against the
committed FEMTO acceleration acquisitions. Upload preparation adds canonical
headers to the two acceleration columns while preserving their original decimal
text. The offline reference independently reads the same acquisitions through
`FemtoAdapter` and `pipeline.canonical_feature_row`. Temperature features are not
compared because this raw-upload contract accepts acceleration only.

The tests observe the actual arrays passed to feature extraction and the actual
ordered DataFrame passed to the serving estimator, without replacing computation.
Chunk sizes of 997 and 4096 exercise split-window and single-chunk parsing.
Samples, window boundaries, feature names, model-column order, sequence indices,
and severity stages must match exactly. Features, model inputs, and HI use
relative and absolute tolerances of `1e-12`, allowing only float64 roundoff.
RUL uses relative tolerance `1e-12` and absolute tolerance `1e-9` seconds to allow
parallel tree-sum reduction order; hours use `1e-12` for both tolerances.
These tolerances are numerical allowances, not accuracy or confidence claims.

RUL is compared with `modeling.predict_tree_baseline` using an independently
loaded artifact. HI and stages are compared with `health.apply_reference_hi`
and `stages.assign_stages`. Single acquisitions must withhold HI. A fixed
60-acquisition alternation of the two fixtures exercises HI history processing;
this artificial sequence is only plumbing evidence, not a real bearing history,
a validated healthy reference, or a held-out evaluation. No model is fitted.

Artifact-dependent cases skip with the missing artifact names when the model
mount is unavailable; preprocessing/feature cases still run. This coverage does
not establish parity with a live deployment or validate non-FEMTO inference.
Any unexplained mismatch blocks release and must be investigated rather than
hidden by widening tolerances.
