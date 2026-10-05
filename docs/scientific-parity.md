# Scientific parity and release audit

Audit of the served raw-data path against the trusted offline pipeline, the leakage
rules, and the fail-closed rules. Base: commit 3613469 (via the m12-reconcile branch).
Every number below was produced by code executed in this audit. Nothing was copied from
earlier reports.

- Evidence generator: `scripts/audit_scientific_parity.py`, which writes
  `reports/verification/scientific-parity-evidence.json`.
- Regression suite: `tests/test_scientific_parity.py` (22 tests).
- Related, pre-existing parity suites: `tests/test_parity.py` and `tests/test_analyze_rul.py`.

Reproduce:

```text
python scripts/audit_scientific_parity.py
python -m pytest -q tests/test_scientific_parity.py tests/test_parity.py tests/test_analyze_rul.py
```

## Data used (real data only, all committed or checksum-pinned)

| Source | What it is | Used for |
|---|---|---|
| `data/fixtures/femto/Bearing1_1/acc_0000{1,2}.csv` | Two real, complete FEMTO acquisitions as the original CSV text | Exact-text parity, temporal-order checks, leakage spy |
| `deploy_data/raw_signal_samples.parquet` | 9 real FEMTO acquisitions: Bearing1_1, Bearing2_1 and Bearing3_1, 3 each, early/mid/late life. Also 3 college-rig recordings | Chunked-vs-offline feature parity, `/analyze/rul` parity, real out-of-domain check |
| `deploy_data/feature_snapshot.parquet` | Offline feature rows: 4,229 FEMTO learning acquisitions plus 3 college rows | Trusted reference features, HI trajectories, artifact prediction parity |
| `artifacts/models/*` | Served artifacts. All 8 match `manifest.json` sha256 (measured) | Model, HI, stages, applicability |

The full FEMTO archives under `datasets/femto/*.zip` are Git LFS pointer files (134 bytes) in this
checkout, so they were not used. The hidden-set predictions in `deploy_data/hidden_set_evaluation.json`
could not be re-derived because the snapshot holds no test-bearing feature rows.

## Path audited

| Stage | Served code | Offline reference | Evidence |
|---|---|---|---|
| Raw FEMTO acquisition | `/predict/rul/femto-acquisition` (+`/blob`); `/analyze/rul` (headered two-axis CSV of concatenated acquisitions) | `femto.read_acceleration`, `adapters.FemtoAdapter` | Below |
| Validation | `_process_femto_acquisition_file`; `_analyze_spooled` validation stage (`chunked.scan_csv_column`) | `read_acceleration` rejects any missing cell | Fail-closed matrix |
| Compatibility | `model_compatibility` (dataset id, sampling rate within 1e-6, feature schema), units must be `g`, `femto-acquisition-v1` preprocessing contract | — | `tests/test_analyze_rul.py::test_metadata_gates_never_infer` |
| Applicability/OOD | `_assess_applicability` → `applicability.assess` (frozen training median/MAD and kNN reference) | `routing.py` uses the same function | Applicability section |
| Preprocessing / windowing | Framing only: 2560-sample windows, no overlap, no filter, resample, pad or impute | Offline: one acquisition = one window | Row accounting |
| Features (time domain + FFT) | `chunked.iter_csv_window_features` → `features.time_domain_features` / `frequency_domain_features` at 25,600 Hz | `pipeline.canonical_feature_row` (same functions) | Parity table |
| Health Indicator | `/predict/hi` → `health.apply_reference_hi`, `stages.assign_stages` | Same functions on the offline frame | Parity table |
| Model routing | `rul_selected_model.json` → `extra_trees` → `rul_extra_trees.joblib` | `modeling.predict_tree_baseline` | Parity table |
| RUL | `/predict/rul` core `_predict_rul_from_features` | `predict_tree_baseline` | Parity table |

FFT validity: frequency features are computed only when there is a sampling rate. The rate comes
either from the caller or from regular timestamps in seconds, and for the model path it must equal
25,600 Hz. The trained features use a one-sided `rfft` over exactly 2560 samples, so the bins are
10 Hz apart and Nyquist is 12,800 Hz.

## Numeric tolerances (defined before comparison)

| Quantity | Tolerance | Why |
|---|---|---|
| Per-window features, chunked vs offline snapshot | rel 1e-12, abs 1e-12 | float64 summation-order roundoff only |
| RUL, served vs offline | abs 1e-9 s | Same input row and same deterministic trees |
| HI, served vs offline | abs 1e-12; stages must be identical | Same functions |
| Artifact predictions, served loader vs direct `joblib.load` | Exact equality | Same bytes |

**Storage-precision caveat.** `deploy_data/raw_signal_samples.parquet` stores samples as float32.
Compared naively, the features differ by up to 2.6e-6 relative (measured): that is storage
precision, not pipeline error. FEMTO records 3-decimal text, and the shortest float32 repr gives
that text back exactly. `recorded_samples()` uses this to recover the original values, and the
recovery is verified to be bit-exact on the text fixture
(`test_recorded_sample_recovery_is_exact_on_the_text_fixture`). All comparisons use the recovered
samples.

## Results (executed)

| Check | Result |
|---|---|
| Chunked extractor vs offline snapshot: 9 real acquisitions × 2 axes × chunk sizes {1, 7, 997, 2559, 2560, 2561, 4096, 65536} (48 runs) | max abs diff 4.66e-10 (absolute, so dominated by the largest-magnitude features), max rel diff 4.44e-14. Within tolerance |
| Same check on exact CSV text (fixture `acc_00001`) | max rel diff 2.07e-16 |
| Row accounting (all 48 runs) | `rows_read == rows_in_file == rows_covered + trailing`, trailing = 0, windows exactly `[i·2560, (i+1)·2560)` |
| `/analyze/rul` on each 3-acquisition real run vs `predict_tree_baseline` on the snapshot row | Bearing1_1 1410.0 s vs 1410.0 s; Bearing2_1 460.0 vs 460.0; Bearing3_1 260.0 vs 260.0; abs diff 0.0. All three HIGH / FULLY_SUPPORTED |
| Served loader vs direct `joblib.load`, 4,229 snapshot rows | max abs diff 0.0 s |
| Artifact identity (in-sample, **not accuracy**) | Predictions on the training rows reproduce their labels exactly (max abs error 0.0 s). This is expected for `bootstrap=False`, `min_samples_leaf=1` ExtraTrees, and it confirms the served artifact is the one fit on these rows |
| Manifest checksums | 8/8 artifacts match; the `deploy_data/` copies of reference HI, stage thresholds, naive model and selection JSON are byte-identical to `artifacts/models/` |
| `/predict/hi` vs offline `apply_reference_hi` + `assign_stages`, full trajectories, rows submitted **shuffled** | Bearing1_1 (2803 rows), Bearing2_1 (911) and Bearing3_1 (515): max abs HI diff 0.0, stages identical, output restored to `sequence_index` order |

## Chunked processing never silently drops rows/windows

- The extractor reads every row. `WindowReport` exposes `rows_read`, `windows_emitted` and
  `trailing_partial_rows`, and the identity `windows·2560 + trailing == rows_read == file rows` is
  asserted for every chunk size above. It is also asserted with 1 and 2559 surplus rows
  (`test_chunked_reports_every_unwindowed_row`).
- Blank lines are kept as missing samples (`skip_blank_lines=False`) instead of being dropped, so
  window boundaries cannot shift (`tests/test_chunked.py::test_blank_rows_preserved`).
- `/analyze/rul` refuses to predict when rows would go unused or when the window count is
  truncated. Surplus rows → `INCOMPLETE_RUN`. Over 200 acquisitions (response cap) →
  `INCOMPLETE_RUN`. Any missing sample → `INCOMPLETE_ACQUISITION`. A window-count mismatch
  between the validation scan and the extractor → 500 `FEATURE_EXTRACTION_FAILED` with no partial
  result.
- `/analyze/features` (no model) may return only the first 200 windows. It then says so
  (`truncated`, `truncation_note`), reports the exact `windows_total`, and reports the unused
  trailing samples in the preprocessing stage detail.

## Leakage audit

| Rule | Finding | Evidence |
|---|---|---|
| No scaler fit on inference data | None is fit. Applicability uses the frozen training median/MAD (`ApplicabilityModel.center/scale`). The tree has no scaler. Missing features are filled with `median_fill`, which is computed from the training frame in `fit_tree_baseline` | `test_inference_never_fits_on_uploaded_data`: every sklearn `fit`/`partial_fit`/`fit_transform`/`fit_predict` is spied during a full `/analyze/rul` request. The only calls are `NearestNeighbors.fit` on the frozen 5,000-row **training** reference (asserted array-equal), and the reference is unchanged afterwards |
| No PCA / feature selection fit on inference data | None on the serving path. The PCA HI artifact is not served. The feature list is the artifact's frozen 44 columns | Same spy test |
| No future lifecycle information | The RUL features are 44 per-acquisition vibration statistics, with no elapsed time, sequence index or run length. `/analyze/rul` predicts from the **latest** acquisition only. HI smoothing is a trailing rolling median (`health._degradation_score`) | Feature list in `rul_extra_trees.joblib`; `tests/test_applicability_routing.py::test_causal_levels_use_only_the_past` |
| No test-set tuning | No tuning happens at serving time. The applicability fit refuses held-out roles (`assert_no_leakage`) | `test_applicability_refuses_to_fit_on_held_out_roles`, `test_test_bearing_labels_cannot_influence_model_or_calibration` |
| Correct temporal order | HI sorts by `sequence_index` before the reference window and rolling (proven with shuffled input above). `/analyze/rul` uses file order and checks a numeric timestamp column for strict increase when one is present. The raw acquisition endpoint now rejects backwards row clocks (defect 1) | `test_served_hi_matches_offline_and_restores_temporal_order`, `test_reordered_acquisition_rows_fail_closed` |

Design note, not a defect: the reference HI centres each run on the median of **that run's own**
acquisitions 10–59. That median is a per-run offset taken from the uploaded data, while scales and
anchors stay frozen from training (docs/decisions.md D18). For acquisitions 0–59 the baseline
therefore includes up to ~10 minutes of later acquisitions. The HI is not an input to the RUL
model, so this cannot leak into RUL.

## Fail-closed matrix (all executed in the suite)

| Input | Result | Test |
|---|---|---|
| Wrong column count / non-numeric cell / header row | 422 `ADAPTER_REQUIRED` / `MALFORMED_FILE` | `tests/test_api_e2e.py`, `tests/test_api_errors.py` |
| Truncated or concatenated single acquisition (≠2560 rows) | 422 `INCOMPLETE_ACQUISITION`, never trimmed or padded | `test_raw_femto_csv_upload_rejects_an_incomplete_or_concatenated_acquisition` |
| Missing vibration sample | 422 `INCOMPLETE_ACQUISITION` | `test_raw_femto_csv_upload_rejects_missing_samples`, `test_missing_samples_reject_before_prediction` |
| Reordered rows (new) | 422 `SAMPLES_OUT_OF_ORDER` | `test_reordered_acquisition_rows_fail_closed` |
| Missing timestamp cell (new) | 422 `INVALID_TIMESTAMPS` | `test_acquisition_with_missing_timestamp_fails_closed` |
| Midnight rollover inside an in-order acquisition | Accepted; RUL identical to the unshifted clock | `test_in_order_acquisition_across_midnight_is_accepted` |
| Infinite / overflowing samples | 422 `NON_FINITE_SIGNAL` / `NON_FINITE_FEATURES` | `tests/test_api_e2e.py`, `test_data_gates` |
| Partial multi-acquisition run | 422 `INCOMPLETE_RUN` | `test_data_gates[partial]`, `test_chunked_reports_every_unwindowed_row` |
| Wrong dataset / rate / units / preprocessing / window / overlap | 422, no inference | `test_metadata_gates_never_infer` |
| Stale local model (sha ≠ manifest) (new) | 503 `MODEL_UNAVAILABLE` | `test_served_model_with_mismatched_checksum_is_unavailable` |

## Applicability

- **LOW suppresses prediction.** On a real FEMTO recording that the frozen gate scores LOW:
  422 `APPLICABILITY_LOW`, `compatibility: RETRAIN_REQUIRED`, no `rul_seconds`
  (`test_real_low_applicability_recording_gets_no_rul`). Real college-rig recordings #201 and
  #2014, submitted as FEMTO features: 422 `APPLICABILITY_LOW`, no RUL.
- **MEDIUM is experimental.** On a real MEDIUM recording: 200, `compatibility: RETRAIN_REQUIRED`,
  and the first reason reads "model applicability is MEDIUM: prediction returned, but treat it
  as experimental ..."
  (`test_real_medium_applicability_recording_is_experimental`). College recording #3827 lands here
  at MEDIUM: an RUL is returned, but only labelled RETRAIN_REQUIRED/experimental.
- **HIGH** on a real recording → FULLY_SUPPORTED (`test_real_high_applicability_recording_is_fully_supported`).
- Measured per-recording levels on the snapshot's training bearings (same single-row rule as
  `/predict/rul`):

  | Bearing | All recordings H / M / L | Last 10 % of life H / M / L |
  |---|---|---|
  | Bearing1_1 | 2702 / 69 / 32 | 217 / 45 / 19 |
  | Bearing2_1 | 862 / 40 / 9 | 61 / 24 / 7 |
  | Bearing3_1 | 509 / 2 / 4 | 47 / 2 / 3 |

## Defects found and fixed

1. **Reordered or timestamp-less raw acquisitions received a FULLY_SUPPORTED RUL.**
   `/predict/rul/femto-acquisition` never checked the row clock. Shuffling rows leaves all 28
   time-domain features unchanged but destroys the spectrum, so a meaningless FFT went straight
   into the model. Missing timestamp cells were also accepted, although the offline reader
   (`femto.read_acceleration`) rejects them.
   - Fix (`src/bearing_pdm/api.py`): reject non-finite timestamps (`INVALID_TIMESTAMPS`) and any
     backwards step of the hour/minute/second/microsecond clock (`SAMPLES_OUT_OF_ORDER`). The
     check is non-decreasing rather than strict because the archive's `%.5g` microsecond field
     can round adjacent samples to equal values, and one midnight rollover is unwrapped.
   - In-order files are unaffected (the whole suite passes unchanged).
2. **A stale local artifact was served without checking the manifest.**
   `artifacts.ensure_artifact` returned any local `artifacts/models/<name>` as-is, even when
   `manifest.json` beside it records a different sha256. A retrained-but-unregistered model would
   have served predictions under a new version hash, with nothing marking it as unvalidated.
   - Fix (`src/bearing_pdm/artifacts.py`): when the manifest beside the file lists a sha256, the
     local file must match it, or it is refused (→ 503 `MODEL_UNAVAILABLE`).
   - With no manifest beside the file, or no recorded checksum, local-development behaviour is
     unchanged. The digest is cached per (path, size, mtime) so large artifacts are hashed once.

## Limitations and open decisions

- **Resolved (2026-10-05, production release policy fix, M2): applicability unavailable →
  RETRAIN_REQUIRED, not FULLY_SUPPORTED.** If `cross_domain_bundle.joblib` cannot be loaded but
  the RUL model can, `/predict/rul` (and everything built on it: `/predict/rul/femto-acquisition`,
  its blob variant, `/analyze/rul`) now returns the RUL with `compatibility=RETRAIN_REQUIRED` -
  the same "prediction returned, but treat it as experimental" contract already used for MEDIUM
  applicability - and `applicability_reasons` states plainly that domain-fit was never checked,
  not confirmed to be fine. History records `APPLICABILITY_NOT_ASSESSED` as before, but
  `compatibility_state` now reflects `RETRAIN_REQUIRED`. No new API state was introduced. This
  was flagged as an open design question by an earlier audit pass (previously pinned by
  `tests/test_history.py`/`tests/test_reliability.py` as FULLY_SUPPORTED); both are updated to
  pin the corrected behavior. The withhold-entirely alternative (mirroring LOW's 422 suppression)
  was considered and rejected: "the gate could not run" is a missing-dependency state, not a
  confirmed-bad-input state, so experimental-but-returned is the smaller, more defensible
  departure from existing architecture.
- **Applicability calibration is conservative on near-failure data.** The threshold is calibrated
  on per-bearing *median* distances but applied to *single* recordings. Even training bearings
  therefore get LOW on 0.8–1.1 % of recordings, and MEDIUM or LOW on 1.2–5.4 %. These are
  concentrated in the last 10 % of life (table
  above), which is where an RUL is most useful. This fails closed (suppression, never
  fabrication). Changing it is a methodology change that needs its own benchmark (model.md §2,
  Opus-level review).
- **Small raw-data parity sample.** 9 + 2 real raw acquisitions from 3 learning bearings are
  covered. The HI and artifact checks cover all 4,229 snapshot rows, but those are training
  bearings, so in-sample agreement proves identity, not accuracy. Held-out accuracy is reported
  separately in `deploy_data/rul_evaluation.json` and `hidden_set_evaluation.json`, and this audit
  did not re-derive it.
- **Order and acquisition boundaries in `/analyze/rul` are caller declarations** unless the upload
  carries a numeric timestamp column. The response says so in `warnings`.
- **Band-energy fractions exclude the Nyquist bin** (12,800 Hz, `freqs < hi`), while total power
  includes it, so the three fractions sum to slightly below 1. The model was trained this way.
  Changing it would alter the trained feature definitions, so it is recorded, not changed.
- **Reliability block.** `reports/metrics/rul_evaluation.json` is absent from this checkout (a copy
  exists in `deploy_data/`), so the held-out-error part of `reliability` is reported as unavailable
  with a reason, never invented.
- **Frontend not re-run.** The frontend test/lint/build commands could not be executed in this
  session (the command required interactive approval). No frontend file was changed.

## Commands executed for this report

```text
python -m pytest -q                         -> 728 passed, 12 skipped (skips: missing
                                               reports/metrics/rul_evaluation.json and cached
                                               feature batches, unchanged from baseline)
python -m ruff check .                      -> All checks passed!
python scripts/audit_scientific_parity.py   -> reports/verification/scientific-parity-evidence.json
```
