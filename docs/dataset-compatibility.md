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
| `RETRAIN_REQUIRED` | Structurally clean and metadata known, but either (a) the sampling rate doesn't match any currently trained model's domain (`_KNOWN_MODEL_SAMPLE_RATES_HZ`, currently FEMTO only, 25.6kHz ± 1%), or (b) the rate matches but the **signal itself** doesn't look like the training population — `applicability.py`'s real HIGH/MEDIUM/LOW domain-fit check (see below) came back MEDIUM or LOW. Either way: no existing model was validated for this configuration. |
| `FULLY_SUPPORTED` | Sampling rate matches a trained model's domain **and** `applicability.py` scores the extracted signal HIGH against that model's training population. A matching rate alone is never sufficient. |

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

### Real model-domain compatibility (`applicability.py`)

Once the structural checks pass and a sampling rate matches a trained model's
rate, `/dataset/inspect` no longer stops there. `_extract_generic_vibration_features`
runs the same `features.py` extraction functions `/predict/rul/femto-acquisition`
uses, on whichever usable high-confidence vibration column(s) the file has, at the
resolved sampling rate.

**Windowing.** The applicability reference population is fitted on FEMTO's fixed
acquisition size (`FEMTO_ACQUISITION_SAMPLES` = 2560 samples). Several features
(total spectral energy, min/max, peak-to-peak, crest factor, spectral
resolution) scale with window length, so scoring an arbitrarily long upload as
one window would compare apples to oranges regardless of how in-domain the
signal itself is (found in review: two real, individually-HIGH acquisitions
concatenated into one file scored MEDIUM purely from length). The file is
instead chopped into `FEMTO_ACQUISITION_SAMPLES`-sized windows, each a
genuine "recording" of one run:
- A file **shorter** than one window is never scored here at all - that's the
  same length mismatch in the other direction. It degrades honestly (like a
  missing bundle, below), not a fabricated domain-shift verdict.
- A file **longer**, not an exact multiple of the window size: the trailing
  remainder that doesn't fill a full window is dropped, and the response says
  so explicitly (`"N trailing row(s) ... were not scored"`) - never silent.
- **Exactly one** window (the common case: most uploads are one acquisition)
  is scored with `single_recording=True` - the same single-row missing-feature
  semantics the raw FEMTO upload endpoint uses for its own single acquisition
  (see `applicability.py`'s own docstring on that parameter: a whole-run's
  missing-feature cap uses the worst column's across-many-rows rate, which
  degenerates to "any one missing feature ⇒ LOW" for a single row). **More
  than one** window uses the normal whole-run `single_recording=False` path -
  genuinely multiple recordings of one run, exactly what `assess()` was
  designed for.

The resulting feature row(s) are scored against the matching trained model's
fitted `ApplicabilityModel` (loaded from `artifacts/models/cross_domain_bundle.joblib`,
`routing.candidates_from_bundle`'s `"raw_seconds"` candidate for FEMTO) - the
exact same HIGH/MEDIUM/LOW decision `routing.py` uses for the offline batch
pipeline, not a reimplementation.

- HIGH → `FULLY_SUPPORTED`.
- MEDIUM or LOW → `RETRAIN_REQUIRED`. The reason text attributes the real
  cause - an elevated feature-distribution shift, missing model feature(s),
  partly-missing model feature(s) (a channel present in some windows of a
  multi-window upload but not others), or a combination - rather than always
  blaming "the signal itself" when the true cause might be a sensor channel
  the upload simply lacks or intermittently drops.
- Bundle artifact missing, unreadable, feature extraction fails, or the file
  is too short for one window → `FULLY_SUPPORTED` with an explicit reason
  stating applicability could not be assessed and the result reflects
  sampling-rate compatibility only - never silently claimed as a full
  domain-fit pass.

The same check runs on `/predict/rul` and `/predict/rul/femto-acquisition`
before they return a prediction (see below) - "every dataset is checked for
real model-domain compatibility before RUL inference," not just at the
inspection step.

## What it deliberately does NOT check

This is a check on one file, run before any adapter parses it. It does not:

- Verify a declared unit's correctness (see above) — only that one was
  declared at all.
- Run the trained applicability model against anything beyond the extractable
  vibration columns' own feature values - operating metadata checks inside
  `applicability.assess()` (sampling rate, rpm, radial load, life time-scale)
  that need columns an arbitrary single-file upload doesn't carry (rpm, load,
  elapsed time) are silently inapplicable, not guessed.

A `FULLY_SUPPORTED` result from this endpoint means the file's columns, its
declared/derived sampling rate, and the extracted signal's statistical
distribution all look usable — it is not a claim that the full pipeline
(preprocessing → HI → RUL) has been run end-to-end against it, and it is not
a substitute for the `quality_gate` checks the batch pipeline runs downstream.

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

## Applicability on the prediction endpoints themselves

`_predict_rul_from_features` (shared by `POST /predict/rul` and
`POST /predict/rul/femto-acquisition`) runs the same `_assess_applicability`
check on the submitted/extracted feature row, on the caller's own values
*before* median-fill (the question is whether what was actually measured
looks in-domain, not whether a filled-in row would):

- LOW → the request is refused with 422 ("RUL suppressed") — mirroring
  `routing.py`'s own `RUL_SUPPRESSED` decision for the offline pipeline. No
  number is returned.
- MEDIUM → the prediction is still returned (200), but `compatibility` is
  `RETRAIN_REQUIRED` and `applicability_reasons` leads with an explicit
  "treat this as experimental" caveat — mirroring `RUL_EXPERIMENTAL`.
- HIGH → `compatibility` is `FULLY_SUPPORTED`.
- Bundle/candidate unavailable → `applicability_level` is `None`,
  `compatibility` defaults to `FULLY_SUPPORTED` (rate/structural checks only,
  same degrade-honestly behaviour as `/dataset/inspect`).

`PredictRulResponse` carries `compatibility`, `applicability_level`,
`applicability_shift_ratio`, and `applicability_reasons` so a client never has
to call `/dataset/inspect` separately to know why a number came back
experimental, or why it didn't come back at all.

## Frontend wiring (`frontend/src/app/upload/page.tsx`)

The upload page asks the user to pick a dataset type *before* choosing a file - "FEMTO /
supported bearing acquisition" (routes straight to `predictRulFromFemtoAcquisition`, i.e. this
endpoint) or "Unknown / other dataset" (routes to `inspectDataset`, with optional declared
sampling-rate/units fields shown only for this path). This mirrors the backend split exactly:
the frontend never infers which route to use from the file's own bytes, because the backend
itself refuses to.
