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

## What it deliberately does NOT check

This is a **column/header-level** check on one file, run before any adapter
parses it. It does not:

- Run the trained applicability/OOD model (`applicability.py`) — that needs
  parsed, feature-extracted recordings from a known adapter, not an arbitrary
  raw upload, and answers a different question ("is this bearing's behavior
  in-distribution for the trained model"), not "is this file structurally
  parseable."
- Determine sampling rate or units — `profiler.py`'s own docstring is explicit
  that a headerless file cannot be mapped by name, and this endpoint never
  guesses one.
- Decide `RETRAIN_REQUIRED` as a distinct state from `ADAPTER_REQUIRED` — that
  distinction needs to know whether an adapter *could* be written for the
  format (structural) versus whether the sensor set is present but the model
  needs re-fitting for a new machine (scientific), which this header-only
  check cannot tell apart. Currently both surface as `ADAPTER_REQUIRED`.

A `FULLY_SUPPORTED` result from this endpoint means the file's columns look
usable — it is not a claim that the full pipeline (feature extraction → HI →
RUL) has been run against it, and it is not a substitute for the
`quality_gate`/applicability checks the batch pipeline runs downstream.

## Raw-upload → RUL for a known format: `POST /predict/rul/femto-acquisition`

This endpoint does not use `_classify`/`profile_file` at all — it is a separate route for a
single named, fixed format: FEMTO's `acc_*.csv` (headerless, 6 positional columns, 25.6kHz).
A headerless file can never be classified `FULLY_SUPPORTED` by `/dataset/inspect` (above),
because column meaning can't be read from names that don't exist — that is correct, documented
behaviour for the generic inspector, not a gap. This route instead takes the caller's explicit
assertion "this is a FEMTO acquisition" (the route itself, not a `dataset_id` field, carries
that contract) and validates the *structural* claim before extracting features: exact column
count, a row-count floor, and finite raw vibration samples. It then runs `features.py`'s real
extraction functions and the same `/predict/rul` inference path, which treats any resulting
non-finite *derived* feature (e.g. a degenerate/zero-variance window makes
`frequency_domain_features` return NaN by design) as missing rather than feeding it to the
model, and fails closed with 422 if a feature value overflows to infinity. It still never
guesses a sampling rate or unit for an unknown format — FEMTO's rate is a documented constant
of this one named adapter, not inferred from the upload. It also cannot detect swapped axes or
wrong units in a headerless file; the caller's "this is a FEMTO acquisition" assertion is
trusted, not independently verified.
