# Dataset compatibility gate (`POST /dataset/inspect`)

Implements goals.md's "automatically inspect the uploaded dataset structure" /
"detect whether an uploaded dataset is compatible" / "fail closed" requirements,
for a single uploaded file, before anything is parsed by an adapter or fed to a
trained model.

## What it checks

Reuses `profiler.profile_file` (delimiter/header sniffing, column-name mapping
against `profiler.ALIASES`, and per-column numeric/NaN/constant checks) rather
than re-implementing any of that. `_classify()` in `src/bearing_pdm/api.py`
turns the profile into one of:

| State | Meaning |
|---|---|
| `INVALID_INPUT` | Unreadable, empty, no data rows, or every recognised vibration column is non-numeric/constant/mostly-missing. |
| `ADAPTER_REQUIRED` | No header (names can't be checked at all), or a vibration channel was only matched by a low-confidence name guess. |
| `UNSUPPORTED` | Has a header, but no column name resembles a vibration channel at all. |
| `FULLY_SUPPORTED` | At least one vibration column mapped with high confidence, numeric, non-constant, ≤50% missing (same `MAX_NAN_FRACTION` as `routing.quality_gate`). |

## `required_action`

Every response also carries `required_action: {kind, message, missing: [..]}`
naming exactly what is missing. `compatibility`, `reasons` and `profile` are
unchanged.

| State | `kind` | `missing` |
|---|---|---|
| `INVALID_INPUT` (unreadable/empty) | `FIX_INPUT_FILE` | a readable, non-empty tabular file |
| `INVALID_INPUT` (header, no rows) | `FIX_INPUT_FILE` | data rows |
| `INVALID_INPUT` (no usable vibration column) | `FIX_INPUT_FILE` | one vibration channel that is numeric, non-constant, finite and at most 50% missing |
| `ADAPTER_REQUIRED` (no header) | `ADAPTER_REQUIRED` | column mapping (an adapter in `src/bearing_pdm/adapters.py`); `sampling_rate_hz` and vibration units as user-provided metadata, since a headerless file carries neither |
| `ADAPTER_REQUIRED` (low-confidence match) | `ADAPTER_REQUIRED` | a confirmed column mapping for the named columns (adapter or explicit mapping) |
| `UNSUPPORTED` | `NO_VIBRATION_CHANNEL` | a vibration channel. Without one this is a different prediction problem, not fixable by an adapter or retraining (unless vibration exists under an unrecognised name, in which case an adapter with an explicit mapping is needed) |
| `FULLY_SUPPORTED` | `STRUCTURAL_CHECK_ONLY` | nothing structural; see below |

### `FULLY_SUPPORTED` means "structurally parseable"

It does **not** mean a trained model is validated for this machine, and
sampling information is reported separately; sensor units are not determined here. Whether an existing model
applies, or a retrain is needed, is decided downstream by routing and
applicability (cached FEMTO-fit models are never applied to other datasets,
`docs/decisions.md` D11). The `required_action` message for this state says
so explicitly.

### `RETRAIN_REQUIRED` is never emitted (by this endpoint)

`model.md` defines it (different machine domain, operating regime or feature
schema; model not scientifically justified). That cannot be decided from a
header-level check, and no heuristic is invented to fake it, so this endpoint
never returns that state. `POST /models/compatibility` (below) does emit it,
because it is given the dataset identity and feature schema it needs.

### Missing-value wording

A vibration column is rejected only when its missing fraction is **greater
than** 50%; exactly 50% is accepted. The reason therefore reads
`more than 50% missing (N% rounded); at most 50% is accepted` so a rounded
figure is not mistaken for a rejection at the threshold itself.

## What it deliberately does NOT check

This is a **column/header-level** check on one file, run before any adapter
parses it. It does not:

- Run the trained applicability/OOD model (`applicability.py`) — that needs
  parsed, feature-extracted recordings from a known adapter, not an arbitrary
  raw upload, and answers a different question ("is this bearing's behavior
  in-distribution for the trained model"), not "is this file structurally
  parseable."
- Guess sampling rates or sensor units. A headerless upload needs explicit metadata.
- Decide `RETRAIN_REQUIRED` as a distinct state from `ADAPTER_REQUIRED` — that
  distinction needs to know whether an adapter *could* be written for the
  format (structural) versus whether the sensor set is present but the model
  needs re-fitting for a new machine (scientific), which this header-only
  check cannot tell apart. Currently both surface as `ADAPTER_REQUIRED`.

A `FULLY_SUPPORTED` result from this endpoint means the file's columns look
usable — it is not a claim that the full pipeline (feature extraction → HI →
RUL) has been run against it, and it is not a substitute for the
`quality_gate`/applicability checks the batch pipeline runs downstream.

## Sampling information

Every inspection response includes `sampling` with `rate_hz` (number or null),
`source` (`metadata`, `timestamps`, `user`, or `unknown`), `regular` (boolean or
null), `required` (whether a rate still needs to be supplied), and `message`.
This is separate from structural compatibility and does not authorize model use.

Supply an explicit rate with the query parameter `sampling_rate_hz`. It must be
finite, greater than zero, and at most 1,000,000 Hz (an input validation ceiling,
not a claim of validated hardware support). Invalid values return HTTP 422
(`VALIDATION_ERROR`).
An explicit value takes precedence and is echoed with source `user`; it does
not prove regular sampling, and any detected irregularity remains in `regular`.

Without a user value, the shared profiler logic derives Hz only from a single
recognized timestamp column with numeric seconds explicitly named `time_s` or
`seconds`, or ISO date-time values with a date and time. Numeric `time`, `t`,
and `timestamp` columns have ambiguous units and require metadata. At least
three timestamps are required. Every uploaded interval must be finite, positive,
and within 1% of the median interval (relative tolerance 0.01, absolute tolerance
zero). The rate is the reciprocal of that median. The timestamp check reads all
rows of the size-limited upload, including rows beyond the structural profile's
sample. Missing, duplicate, reversed, or irregular timestamps yield a null rate.
Absent or insufficient timing evidence yields `regular: null`.

No rate is inferred from row counts, filenames, or a presumed dataset. A single
raw upload has no validated adapter identity, so it cannot currently emit
`metadata`; documented adapter rates remain available to folder profiling.
A missing rate sets `required: true`: frequency analysis needs user or dataset
metadata. Providing a rate does not repair irregular timestamps or establish
sensor units, machine compatibility, or permission to use a cached FEMTO model.

## Upload errors

Files that are not delimited text are refused before profiling with a coded error
instead of a classification: binary content is 415 `UNSUPPORTED_FILE_TYPE`, empty is
422 `EMPTY_UPLOAD`, non-UTF-8 is 422 `UNDECODABLE_FILE`, a giant first line or parser
crash is 422 `MALFORMED_FILE`, and size limits are 413. Every error carries `code`,
`retryable` and `message` alongside `detail`; see `docs/api-errors.md` for the full
catalogue.

# Model compatibility gate (`POST /models/compatibility`)

Answers a different question from `/dataset/inspect`: not "is this file
parseable" but "may the selected cached RUL model be used for this dataset".
It takes metadata only and never produces a prediction
(`prediction_produced` is always `false`).

Request (JSON; no raw data, no feature values):

```json
{"dataset_id": "femto", "feature_names": ["vibration_x_rms", "..."], "sampling_rate_hz": 25600}
```

`sampling_rate_hz` is optional, must be finite, `> 0` and `<= 1,000,000`
(same bounds as `/dataset/inspect`). A body that fails schema validation is
422 `VALIDATION_ERROR`.

## What it compares against

| Check | Source (reused, not duplicated) |
|---|---|
| Selected model | `artifacts/models/rul_selected_model.json` (`selected`), loaded with `_load_joblib`. Only `extra_trees` has a feature schema; any other selection fails closed. |
| Feature schema | The selected model's `feature_columns`, reported with the same `feature_schema_version` fingerprint as `/health` and prediction history. |
| Trained domain | `femto` (`TRAINED_DATASET_ID` in `api.py`). The model artifact carries no domain field; every cached model is fit on FEMTO learning bearings only (`docs/decisions.md` D11). |
| Registered adapters, sampling | `adapters.ADAPTERS` and each adapter's documented `sampling_rate_hz` (published dataset metadata, never inferred). |
| Required signals | Canonical channels (`adapters.VIBRATION_CHANNELS`) that the model's feature names are computed from: `vibration_x`, `vibration_y`. |

## Decision order and justification (model.md section 8)

Rules are applied in this order; the first match wins.

| # | Condition | State | `required_action.kind` | Why this state |
|---|---|---|---|---|
| 1 | Empty `dataset_id`, empty `feature_names`, an empty name, or duplicate names | `INVALID_INPUT` | `FIX_REQUEST` | The request does not describe a dataset; nothing can be compared. |
| 2 | Selected-model metadata missing or unusable | 503 `MODEL_UNAVAILABLE` (retryable) | - | Fail closed: without the trained schema no state can be justified, so none is returned. |
| 3 | `dataset_id` has no registered adapter | `UNSUPPORTED` | `UNSUPPORTED_DATASET` | Section 8 UNSUPPORTED: without an adapter the signals, units and sampling cannot be determined. Matching feature *names* do not change this: names say nothing about the machine, units or rate. |
| 4 | Registered adapter, but not `femto` (`college`, `ims`, `xjtu`) | `RETRAIN_REQUIRED` | `RETRAIN_REQUIRED` | Section 8 RETRAIN_REQUIRED: a materially different machine/operating domain, and D11 forbids applying FEMTO-fit models elsewhere. Returned even when the feature schema matches exactly, so it is never `FULLY_SUPPORTED`. |
| 5 | `femto`, `sampling_rate_hz` supplied and not equal (relative tolerance 1e-6) to the adapter's documented 25,600 Hz | `RETRAIN_REQUIRED` | `RETRAIN_REQUIRED` | 16 of the current model's 44 features are frequency-domain (spectral frequencies in Hz, band-energy fractions, spectral entropy/energy), computed from a spectrum whose axis depends on the rate; a different rate is a different signal regime the model has no validation for. |
| 6 | `femto`, one or more model features not provided | `ADAPTER_REQUIRED` | `ADAPTER_REQUIRED` | Section 8 ADAPTER_REQUIRED: same physical problem and trained domain, but the schema/layout differs. The registered FEMTO adapter plus the project feature pipeline (`pipeline.canonical_feature_row`) deterministically produce exactly the trained schema from the raw recordings without changing model semantics. `missing` lists every absent feature and the required signals. The gate never median-fills; that `/predict/rul` tolerates up to 50% median-filled features is a separate, weaker prediction-time rule this gate does not endorse. |
| 7 | `femto`, every model feature provided | `FULLY_SUPPORTED` | `NONE` | Section 8 FULLY_SUPPORTED: required channels present, units known for the FEMTO adapter (g), sampling compatible (supplied and equal, or the adapter's documented rate with `sampling.source: "adapter_metadata"`), trained schema reproduced, trained domain. Extra features are listed in `feature_schema.extra` and ignored: the model selects its columns by name, so they change nothing. |

`RETRAIN_REQUIRED` is never softened to `ADAPTER_REQUIRED` for another dataset:
an adapter already exists for college, IMS and XJTU-SY; what is missing is a
model validated on their domain.

## Response

`compatibility`, `dataset_id` (trimmed, lower-cased), `reasons`,
`required_action {kind, message, missing}`, `model {name, version,
feature_schema_version, trained_dataset_id}`, `adapter {dataset_id,
display_name, sampling_rate_hz}` (null if unregistered), `feature_schema
{expected_count, provided_count, missing, extra}`, `required_signals`,
`sampling {rate_hz, source, compatible}` and `prediction_produced: false`.
The access log records the state as `compatibility` (stage
`model_compatibility`); feature names are never logged.

## Limitations

- It trusts the caller's `dataset_id`; it does not verify that the data really
  comes from that dataset. `/dataset/inspect` and the batch pipeline's quality
  gate and applicability model (`routing.py`, `applicability.py`) check actual
  data; this gate only checks metadata.
- `FULLY_SUPPORTED` does not mean a given bearing is in-distribution; that
  needs feature values and `applicability.assess`.
- Units are not a request field: they are known only through a registered
  adapter, which is why an unregistered dataset is `UNSUPPORTED`.
