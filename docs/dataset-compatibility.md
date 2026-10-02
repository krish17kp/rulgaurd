# Dataset compatibility gate (`POST /dataset/inspect`)

Implements goals.md's "automatically inspect the uploaded dataset structure" /
"detect whether an uploaded dataset is compatible" / "fail closed" requirements,
for a single uploaded file, before anything is parsed by an adapter or fed to a
trained model.

## What it checks

Reuses `profiler.profile_file` (delimiter/header sniffing, column-name mapping
against `profiler.ALIASES`, and per-column numeric/NaN/constant checks) rather
than re-implementing any of that. `_classify()` in `src/bearing_pdm/api.py`
turns the profile, plus (only for the last step) a sampling rate/units
declaration, into one of:

| State | Meaning |
|---|---|
| `INVALID_INPUT` | Unreadable, empty, no data rows, or every recognised vibration column is non-numeric/constant/mostly-missing. |
| `UNSUPPORTED` | Has a header, but no column name resembles a vibration channel at all. |
| `ADAPTER_REQUIRED` | A structural problem (no header, so names can't be checked at all; or a vibration channel matched only by a low-confidence name guess); a metadata gap (sampling rate unknown and not declared, and/or units not declared); or a `declared_sampling_rate_hz` that conflicts with a rate derived from a real timestamp column (the file's own evidence is never silently overridden). All are "more information or a correction is needed before this is usable," distinguished in the `reasons` text. |
| `RETRAIN_REQUIRED` | Structurally clean (high-confidence vibration column(s), usable values) **and** sampling rate/units are known (declared or derived from a real timestamp column) — but the sampling rate doesn't match any currently trained model's domain (`_KNOWN_MODEL_SAMPLE_RATES_HZ`, currently FEMTO only, 25.6kHz ± 1%). The sensor set and metadata are fine; no existing model was fit for this configuration. |
| `FULLY_SUPPORTED` | All of the above, and the sampling rate matches a trained model's domain within tolerance. |

### Sampling rate and units

Per `ml-data.md`, neither is ever guessed. The sampling rate comes from one of
two sources, both evidence, never the file's shape or row count:
1. A real `timestamp`-mapped column already in the file — `_derive_sampling_rate_hz`
   takes the median step between samples, the same rule `profiler._sampling_rate`
   uses for a multi-file folder profile. **This always wins when present** —
   a declaration cannot override it. If a `declared_sampling_rate_hz` is also
   given and disagrees with the derived rate by more than 1%, the request is
   rejected as `ADAPTER_REQUIRED` with a conflict reason, not silently
   resolved in the declaration's favour.
2. The caller's own `declared_sampling_rate_hz` form field, used only when (1)
   doesn't apply (no timestamp column, or its values aren't numeric/varying).
   Validated to be a finite positive number (422 otherwise) — never validated
   for *correctness* beyond that, since there is no way to check a
   declaration against the file's own bytes when no timestamp exists.

Units have no equivalent derivation path (no column carries a reliably
parseable physical unit), so `declared_units` is a pure declaration: required
for traceability before `FULLY_SUPPORTED`/`RETRAIN_REQUIRED`, but **this
project keeps no verified units contract to check it against** — a wrong
declaration cannot be caught here. That limit is stated in the API's own
`reasons` text, not hidden.

## What it deliberately does NOT check

This is a **column/header-level** check on one file, run before any adapter
parses it. It does not:

- Run the trained applicability/OOD model (`applicability.py`) — that needs
  parsed, feature-extracted recordings from a known adapter, not an arbitrary
  raw upload, and answers a different question ("is this bearing's behavior
  in-distribution for the trained model"), not "is this file structurally
  parseable."
- Verify a declared unit's correctness (see above) — only that one was
  declared at all.
- Compare anything beyond sampling rate against a trained model's domain.
  `RETRAIN_REQUIRED` here means "the rate doesn't match," not a full
  applicability/OOD judgement — a file whose rate *does* match FEMTO's could
  still be out-of-distribution in ways only `applicability.py` (on parsed,
  adapter-produced recordings) can detect.

A `FULLY_SUPPORTED` result from this endpoint means the file's columns, and
its declared/derived sampling rate, look usable — it is not a claim that the
full pipeline (feature extraction → HI → RUL) has been run against it, and it
is not a substitute for the `quality_gate`/applicability checks the batch
pipeline runs downstream.

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

## Frontend wiring (`frontend/src/app/upload/page.tsx`)

The upload page asks the user to pick a dataset type *before* choosing a file - "FEMTO /
supported bearing acquisition" (routes straight to `predictRulFromFemtoAcquisition`, i.e. this
endpoint) or "Unknown / other dataset" (routes to `inspectDataset`, with optional declared
sampling-rate/units fields shown only for this path). This mirrors the backend split exactly:
the frontend never infers which route to use from the file's own bytes, because the backend
itself refuses to.
