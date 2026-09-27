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
