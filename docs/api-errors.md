# API error catalogue

Every error response from the FastAPI service (`src/bearing_pdm/api.py`) is JSON with
four fields:

| Field | Type | Meaning |
|---|---|---|
| `detail` | string, or list for `VALIDATION_ERROR` | Unchanged from earlier versions (FastAPI's field), kept for backwards compatibility. |
| `code` | UPPER_SNAKE string | Stable, machine-readable. Branch on this, not on `detail` text. |
| `retryable` | bool | `true` only if the *same request* could succeed later without the caller changing it. |
| `message` | string | User-readable text. Equal to `detail` when that is a string. |

Every error `code` is also written to the request's access log record, next to the same
`X-Request-ID` (`docs/observability.md`).

Success responses are unchanged. Every error, including the two 413 paths and the last-resort
500, carries CORS headers and `X-Request-ID`, and the API exposes `X-Request-ID` to browsers
(`Access-Control-Expose-Headers`), so a browser client can read the body and quote the id.

## Codes

| Status | `code` | Retryable | When |
|---|---|---|---|
| 413 | `REQUEST_TOO_LARGE` | no | Request body over the limit (64MB upload + 2MB multipart overhead), by declared `Content-Length` or by counted bytes on a chunked request. |
| 413 | `UPLOAD_TOO_LARGE` | no | The uploaded file itself is over the 64MB inspection limit. |
| 415 | `UNSUPPORTED_FILE_TYPE` | no | The upload is binary (NUL bytes, or a zip/xlsx/pdf/gzip/png signature), not delimited text. |
| 422 | `EMPTY_UPLOAD` | no | Zero-byte upload. |
| 422 | `UNDECODABLE_FILE` | no | The first megabyte is not valid UTF-8. Re-save as UTF-8. |
| 422 | `MALFORMED_FILE` | no | No line break in the first megabyte (not row-oriented), or the parser failed on the file. |
| 422 | `VALIDATION_ERROR` | no | Body, query or multipart-field validation (bad JSON, missing `dataset_id`, `sampling_rate_hz` out of range, no `file` part). `detail` is FastAPI's list of errors. |
| 422 | `UNSUPPORTED_DATASET` | no | `dataset_id` is not `femto`; cached models are FEMTO-only (`docs/decisions.md` D11). |
| 422 | `FEATURES_MISSING` | no | Required feature columns absent (RUL: more than 50% or no fallback median; HI: any row lacks a column). |
| 422 | `INSUFFICIENT_ROWS` | no | HI request shorter than the model's reference window. |
| 422 | `NON_FINITE_FEATURES` | no | NaN/inf in HI feature values. |
| 422 | `DEGENERATE_REFERENCE_WINDOW` | no | HI reference window shows no real variation (e.g. stuck sensor). |
| 422 | `ADAPTER_REQUIRED`, `NO_VIBRATION_CHANNEL`, `UNSUPPORTED_DELIMITER`, `CHANNEL_NOT_FOUND`, `CHANNEL_AMBIGUOUS`, `CHANNEL_NOT_VIBRATION` | no | `POST /analyze/features`, `dataset_detection` stage: the file or chosen channel cannot be mapped (see `docs/feature-analysis.md`). |
| 422 | `SAMPLING_RATE_REQUIRED`, `SAMPLING_RATE_CONFLICT`, `TIMESTAMPS_IRREGULAR`, `SAMPLES_OUT_OF_ORDER`, `INVALID_WINDOW`, `INSUFFICIENT_SAMPLES`, `NON_NUMERIC_SIGNAL`, `NON_FINITE_SIGNAL`, `CONSTANT_SIGNAL`, `EXCESSIVE_MISSING` | no | `POST /analyze/features`, `validation` stage. `code` is the first problem; `validation_errors` lists all of them. |
| 422 | `COMPUTE_LIMIT_EXCEEDED` | no | `POST /analyze/features` and `POST /analyze/rul`, `preprocessing` stage: the windows that would be featurised times `window_samples` exceed 16,777,216 samples per channel. Use a smaller window or overlap. |
| 422 | `INCOMPLETE_ACQUISITION` | no | `POST /analyze/rul`, `model_compatibility` stage: under `femto-acquisition-v1` a vibration axis has at least one missing sample. `POST /predict/rul/femto-acquisition` (and `/blob`): the file is not exactly one 2560-row acquisition, or a vibration sample is missing. Checked before any prediction; samples are never dropped, filled, trimmed or padded. Body carries `compatibility: "INVALID_INPUT"`. |
| 422 | `APPLICABILITY_LOW` | no | `POST /predict/rul`, `/predict/rul/femto-acquisition` (and `/blob`), and `POST /analyze/rul` (`prediction` stage): the submitted/extracted features are out of the model's training distribution, so the RUL is suppressed. Body carries `compatibility: "RETRAIN_REQUIRED"`. |
| 422 | `ADAPTER_REQUIRED`, `MALFORMED_FILE`, `NON_FINITE_SIGNAL`, `NON_FINITE_FEATURES` | no | `POST /predict/rul/femto-acquisition`: wrong column count for FEMTO's fixed layout; a non-numeric cell; an infinite vibration sample; samples too extreme to extract finite features from. `NON_FINITE_FEATURES` also covers the same overflow on `/predict/rul`. |
| 422 | `INVALID_BLOB_URL` | no | A `/blob` endpoint's `blob_url` is not an https object in this deployment's Blob store (or contains control characters). |
| 404 | `UPLOAD_NOT_FOUND` | no | A `/blob` endpoint's object does not exist (expired or already cleaned up). Re-upload. |
| 502 | `STORAGE_FETCH_FAILED` | yes | A `/blob` endpoint could not download the object (storage error status or interrupted transfer). |
| 503 | `INVALID_MODEL_OUTPUT` | no | The cached model produced a non-finite RUL (or, on `/analyze/rul`, a negative one); nothing is returned. |
| 422 / 500 | `FEATURE_EXTRACTION_FAILED` | no | `POST /analyze/features`, `feature_extraction` stage: the extractor could not read the validated channel (422) or produced a different window count than validation implied (500). |
| 400 | `MALFORMED_REQUEST` | no | Body that cannot be parsed at the HTTP level (e.g. corrupt multipart framing), if it is not reported as `VALIDATION_ERROR`. |
| 404 / 405 | `NOT_FOUND` / `METHOD_NOT_ALLOWED` | no | Unknown route / wrong method. |
| 503 | `MODEL_UNAVAILABLE` | yes | A cached model or HI artifact is not loadable on this instance (for `POST /models/compatibility`: `rul_selected_model.json` or the selected model's feature schema is missing or unusable). Retry with backoff; if it persists an operator must provide the artifact. |
| 503 | `METRICS_UNAVAILABLE` | yes | `reports/metrics/rul_evaluation.json` is missing. |
| 503 | `STORAGE_UNAVAILABLE` | yes | The service could not spool the upload to temporary storage. |
| 503 | `MEMORY_LIMIT_EXCEEDED` | no | Inspecting the file exhausted memory. Retrying the same file will fail again; upload a smaller one. Best effort: a hard platform OOM kill cannot be turned into JSON. |
| 500 | `INTERNAL_ERROR` | no | Anything unhandled. Body is generic; no traceback or exception text is returned or logged (only the exception type). Report `X-Request-ID`. |

Other HTTP statuses raised by the framework keep a `code` from a default table
(`408 REQUEST_TIMEOUT`, `429 RATE_LIMITED`, `504 GATEWAY_TIMEOUT` are retryable;
unlisted statuses get `HTTP_ERROR`, not retryable).

`POST /analyze/features` errors raised inside the pipeline additionally carry `failed_stage`
and the full `stages` array (and, where relevant, `compatibility`, `required_action` or
`validation_errors`). Upload errors on that endpoint use the same codes as above with
`failed_stage: "upload"`. The middleware-level `REQUEST_TOO_LARGE` and a framework
`VALIDATION_ERROR` (e.g. no `channel`) happen before the pipeline and carry no `stages`.

## Not errors

`POST /dataset/inspect` answers `200` for a readable-or-not file that it *classifies*. An
unparseable or unusable table (ragged rows, header only, non-numeric vibration column, empty
header) is `200` with `compatibility: "INVALID_INPUT"` and
`required_action.kind: "FIX_INPUT_FILE"`; unsupported schemas are `UNSUPPORTED` /
`ADAPTER_REQUIRED` (see `docs/dataset-compatibility.md`). Those carry no `code`/`retryable`
because they are results, not failures; use `required_action.kind`.

`POST /models/compatibility` likewise answers `200` with a `compatibility` state for every
well-formed request, including `UNSUPPORTED`, `RETRAIN_REQUIRED` and `INVALID_INPUT`
(empty/duplicate names). Only a body that fails schema validation is 422 `VALIDATION_ERROR`,
and missing model metadata is 503 `MODEL_UNAVAILABLE`.

## Timeouts

The API has no server-side timeout of its own. A gateway or platform timeout (for example a
Vercel function timeout, HTTP 504) is produced outside this application, usually with a
non-JSON body, so clients must treat a 504, a dropped connection or a non-JSON error body as
retryable at most once or twice with backoff, never in a tight loop.

## Contract and regression tests

`tests/test_api_contract.py::test_public_openapi_contract` compares a freshly generated
OpenAPI document with `tests/fixtures/api_openapi.json`. The snapshot includes every public
route, HTTP method, request schema, response schema, required field, nullable field and
referenced component. Normal test runs never rewrite it. Dictionary-valued response bodies
have deliberately loose OpenAPI schemas; the contract module additionally pins the actual
health, model-info and history envelope fields. Evaluation returns the generated metrics
report verbatim; `test_models_evaluation_returns_real_metrics_with_college_caveat` in
`tests/test_api.py` owns its artifact-dependent response check. The snapshot is a declaration
contract, not proof that every runtime response matches its schema.

For an intentional contract change, review the API and frontend consumers first. From the
repository root, with the project environment activated, regenerate explicitly:

```bash
PYTHONPATH=src python tests/test_api_contract.py --write-snapshot
git diff -- tests/fixtures/api_openapi.json
python -m pytest -q tests/test_api_contract.py tests/test_api.py tests/test_api_errors.py
python -m pytest -q
python -m ruff check .
```

Review the JSON diff before accepting it; regeneration must not be used merely to silence
an unexpected failure. No model values, raw sensor readings, metrics or private paths are
stored in the snapshot.

### Regression ownership

Existing fixtures are reused rather than copied into the contract module. The task's
referenced `SESSION_HANDOFF_2026-09-27.md` is absent from this checkout; this inventory covers
the defect list supplied with Goal 36, second slice.

| Previously fixed defect | Executable regression owner |
|---|---|
| Fail-open non-numeric, constant, NaN/missing or infinite vibration input | `tests/test_api.py`: `test_dataset_inspect_invalid_for_non_numeric_vibration_column`, `test_dataset_inspect_invalid_for_all_missing_vibration_column`, `test_dataset_inspect_invalid_when_every_vibration_column_is_missing`, `test_dataset_inspect_invalid_for_constant_vibration_column`, `test_dataset_inspect_invalid_for_all_infinite_vibration_column`; `tests/test_api_classify.py` also pins mixed channels and the 50% missing boundary. |
| Mostly missing RUL features | `tests/test_api.py::test_predict_rul_rejects_mostly_missing_features`, now asserting `FEATURES_MISSING` and non-retryability. |
| Oversized declared Content-Length | `tests/test_api.py::test_oversized_content_length_is_rejected_before_body_is_read`; `tests/test_api_errors.py::test_content_length_413_has_code_cors_and_request_id`. |
| Oversized chunked request | `tests/test_api.py::test_oversized_chunked_body_stops_being_read_once_limit_is_exceeded`; `tests/test_api_errors.py::test_chunked_413_has_code_cors_and_request_id`. |
| Degenerate HI reference window | `tests/test_api.py`: `test_predict_hi_rejects_constant_reference_window_even_when_long_enough`, `test_predict_hi_rejects_reference_window_with_only_float_jitter`, `test_predict_hi_rejects_reference_window_with_only_one_varying_feature`, now asserting the exact code and non-retryability. |
| Vibration-z-only and header-plus-one-row classifier gaps | `tests/test_api_contract.py::test_inspect_reviewer_regressions`, through the upload endpoint. Structural support does not assert model applicability. |

### Error-code coverage

The following tests exercise the error catalogue without duplicating the original input
fixtures. Model-dependent tests require the mounted artifacts. Existing conditional skips
remain unchanged; the contract module introduces no skips.

| Codes | Executable owner |
|---|---|
| `REQUEST_TOO_LARGE`, `UPLOAD_TOO_LARGE` | The three 413 tests in `tests/test_api_errors.py`. |
| `UNSUPPORTED_FILE_TYPE`, `EMPTY_UPLOAD`, `UNDECODABLE_FILE`, `MALFORMED_FILE` | Binary, empty, undecodable, huge-line and parser-crash tests in `tests/test_api_errors.py`. |
| `VALIDATION_ERROR`, `MALFORMED_REQUEST`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `UNSUPPORTED_DATASET` | Validation, malformed multipart, unknown-route/wrong-method and unsupported-dataset tests in `tests/test_api_errors.py`. |
| `FEATURES_MISSING`, `INSUFFICIENT_ROWS`, `NON_FINITE_FEATURES`, `DEGENERATE_REFERENCE_WINDOW` | HI rejection and mostly-missing RUL tests in `tests/test_api.py`, with exact code assertions. |
| `ADAPTER_REQUIRED`, `NO_VIBRATION_CHANNEL`, `UNSUPPORTED_DELIMITER`, `CHANNEL_NOT_FOUND`, `CHANNEL_AMBIGUOUS`, `CHANNEL_NOT_VIBRATION` | `test_headerless_real_fixture_fails_detection` and `test_channel_and_format_fail_detection` in `tests/test_analyze_features.py`. |
| `SAMPLING_RATE_REQUIRED`, `SAMPLING_RATE_CONFLICT`, `TIMESTAMPS_IRREGULAR`, `SAMPLES_OUT_OF_ORDER`, `INVALID_WINDOW`, `INSUFFICIENT_SAMPLES`, `NON_NUMERIC_SIGNAL`, `NON_FINITE_SIGNAL`, `CONSTANT_SIGNAL`, `EXCESSIVE_MISSING` | Sampling, overlap, short-input, non-numeric, constant and parametrized signal-quality tests in `tests/test_analyze_features.py`. |
| `FEATURE_EXTRACTION_FAILED` | `tests/test_api_contract.py::test_feature_extraction_failure_contract` covers both 422 parser failure and 500 window-count mismatch, failed stage and absence of partial windows. Its synthetic signal and explicit sampling rate are test inputs, not validated machine metadata. |
| `MODEL_UNAVAILABLE`, `METRICS_UNAVAILABLE`, `STORAGE_UNAVAILABLE`, `MEMORY_LIMIT_EXCEEDED`, `INTERNAL_ERROR` | Missing-artifact, spool-failure, memory-error and unhandled-exception tests in `tests/test_api_errors.py`. |
| `REQUEST_TIMEOUT`, `RATE_LIMITED`, `GATEWAY_TIMEOUT`, `HTTP_ERROR` | `tests/test_api_contract.py::test_framework_error_defaults` invokes the registered framework exception handler and pins status, envelope, retryability and header preservation. It also covers the generic `SERVICE_UNAVAILABLE` default. These are handler tests, not simulated external gateway responses. |
| `HISTORY_UNAVAILABLE` (documented in `prediction-history.md`) | `tests/test_history.py::test_history_failure_is_explicit`. |

`tests/test_upload_lifecycle.py` additionally checks cleanup on success, validation,
parser/storage failure, disconnect, cancellation and both body-limit paths across all
three upload routes.
