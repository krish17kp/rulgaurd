# Observability

The API (`src/bearing_pdm/api.py`) writes one structured access record per request with
stdlib `logging` (logger `bearing_pdm.api`, level from `LOG_LEVEL`, default `INFO`) to
stderr. Vercel and container platforms capture that as-is; there is no extra service,
dependency or credential.

## Access record

The message is a `key=value` line; the same fields are also attributes on the `LogRecord`
(`record.stage`, `record.code`, ...), so a JSON formatter or a test can read them without
parsing. Records with status >= 500 are `WARNING`, all others `INFO`.

| Field | Present | Meaning |
|---|---|---|
| `request_id` | always | 12-hex id, also returned as the `X-Request-ID` header; quote it when reporting a problem. |
| `method`, `path` | always | HTTP method and URL path. Control characters in the path are replaced and it is cut at 200 characters, so a request cannot forge log lines. The query string is never logged. |
| `status` | always | HTTP status returned. |
| `duration_ms` | always | Wall-clock processing time of the request, milliseconds. |
| `stage` | always | Endpoint-level pipeline stage: `health`, `model_info`, `model_evaluation`, `predict_rul`, `predict_rul_femto_acquisition`, `predict_rul_femto_acquisition_blob`, `predict_hi`, `prediction_history`, `dataset_inspect`, `dataset_inspect_blob`, `model_compatibility`, `analyze_features`, `analyze_rul`, or `unmatched` (unknown route). The Vercel `/api` prefix is ignored. |
| `model_name` | when a model artifact was loaded for the request | `extra_trees` (`/predict/rul`, `/models/compatibility`) or `reference_hi` (`/predict/hi`). Also set on a failure that happens after the model loaded (for example `FEATURES_MISSING`). |
| `model_version` | with `model_name` | `sha256:` content hash of the artifact file(s) - the same value stored in prediction history. |
| `feature_schema_version` | with `model_name` | `sha256:` fingerprint of the model's ordered feature-column names (not values) - the same value stored in prediction history. |
| `pipeline_stage` | `/analyze/features` failures | The inner stage that failed (`upload`, `dataset_detection`, `validation`, `preprocessing`, `feature_extraction`), same as `failed_stage` in the response body (`docs/feature-analysis.md`). |
| `compatibility` | `/dataset/inspect` and `/analyze/features` when the file was classified | `FULLY_SUPPORTED`, `ADAPTER_REQUIRED`, `UNSUPPORTED` or `INVALID_INPUT`. This is the structural check only, see `docs/dataset-compatibility.md`. On `/models/compatibility`, the model-compatibility state (which can also be `RETRAIN_REQUIRED`). Feature names are never logged. |
| `code` | on every error response | The stable error code from `docs/api-errors.md`, identical to the `code` in the response body. Absent on success. |
| `exc_type` | when an exception was caught or turned into an error | The exception class name only (for example `ValueError`, `OSError`). |

Fields that do not apply are omitted, never logged as `None`. A request the API rejects
before it reaches a model has no `model_*` fields, so an absent `model_name` never implies
that a model was used.

Example (values illustrative):

```
request_id=3f9a1c07be21 method=POST path=/predict/rul status=200 duration_ms=14.2 stage=predict_rul model_name=extra_trees model_version=sha256:... feature_schema_version=sha256:...
request_id=8c2e5d90aa14 method=POST path=/dataset/inspect status=200 duration_ms=6.8 stage=dataset_inspect compatibility=ADAPTER_REQUIRED
request_id=1b77e0c3d5f8 method=POST path=/predict/rul status=422 duration_ms=1.1 stage=predict_rul code=UNSUPPORTED_DATASET
```

## What is never logged

Request bodies, feature or sensor values, prediction results, uploaded filenames, file
contents, query-parameter values (for example `sampling_rate_hz`), exception messages or
tracebacks (parsers quote cell values in them; only the exception type is kept), and
filesystem paths. `tests/test_observability.py` captures the log records and asserts both
that the fields above are present and that sentinel feature values, filenames and exception
text are absent. Prediction summaries are kept in the prediction history store, not the
logs (`docs/prediction-history.md`).

## Diagnosing a failure from the logs

1. Get the `X-Request-ID` from the client (it is exposed to browsers).
2. Find the record with that `request_id`. `code` says what failed, `stage` where, and
   `model_version` / `feature_schema_version` say which artifact was serving.
3. `code=INTERNAL_ERROR` with `exc_type` is an unhandled exception; the message is
   deliberately not logged. `MODEL_UNAVAILABLE` means an artifact was not loadable on that
   instance; `/health` shows which.
4. `duration_ms` on a 5xx or an unusually slow request identifies the stage to profile.

## `GET /health`

`status: "ok"` only says the process is up and serving (liveness). Model readiness is
reported separately:

```json
{
  "status": "ok",
  "ready": true,
  "api_version": "0.1.0",
  "models_loaded": {"rul_extra_trees": true, "rul_naive": true},
  "models": {
    "rul_extra_trees": {"loaded": true, "version": "sha256:...", "feature_schema_version": "sha256:..."},
    "reference_hi":    {"loaded": true, "version": "sha256:...", "feature_schema_version": "sha256:..."}
  }
}
```

- `ready` is `true` only when every artifact the prediction endpoints need is loaded
  (RUL model; reference HI model and stage thresholds). A missing artifact gives
  `ready: false`, `loaded: false` and `version: null` with HTTP 200, so a deployment monitor
  should alert on `ready`, not on the status code alone.
- `models_loaded` is unchanged from earlier versions.
- `version` and `feature_schema_version` are the same hashes as in the access log and the
  prediction history. No file names or paths are returned. `reference_hi.version` covers
  both the HI model and the stage-threshold artifact.
- An artifact that exists but cannot be deserialised makes `/health` fail with the standard
  `500 INTERNAL_ERROR` (logged with `code` and `exc_type`) rather than reporting a loaded
  model.

## Limitations

No metrics endpoint, aggregation or alerting is provided; the platform's log search is the
consumer. `duration_ms` covers the whole request including the history write. Model fields
describe the artifacts that were loaded, which is what handled the request; a hot-swapped
artifact on disk is not re-hashed until the process restarts.

## Upload cleanup

Upload routes add a random `upload_id` and `cleanup_state` for their temporary
analysis file. The final state is `deleted` after successful close/unlink,
`not_created` if creation failed, or `failed` if close/unlink failed. The HTTP
status and error code describe the request outcome independently of cleanup.
No filename or temporary path is logged. See [raw upload lifecycle](upload-lifecycle.md)
for retention, multipart cleanup, disconnect behavior, and process-crash limits.
