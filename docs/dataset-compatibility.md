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

### `RETRAIN_REQUIRED` is never emitted

`model.md` defines it (different machine domain, operating regime or feature
schema; model not scientifically justified). That cannot be decided from a
header-level check, and no heuristic is invented to fake it, so this endpoint
never returns that state.

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
not a claim of validated hardware support). Invalid values return HTTP 422.
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
