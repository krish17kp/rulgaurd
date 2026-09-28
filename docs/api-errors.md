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
