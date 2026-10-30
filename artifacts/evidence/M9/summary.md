# M9 evidence: reproducibility and final scientific audit

Date: 2026-10-30. Scope: the whole pipeline as deployed on forevue.tech, with emphasis on
what changed since M10/M12: the upload health reliability rating, RUL learned per upload
(D32), `.mat`/`.wav` reading, and the M7 number check. M6 (CNN) was not done, at the
owner's instruction, and stays DEFERRED.

## Reproducibility

- `pytest -q` (excluding `test_dashboard.py`/`test_storage.py`, which need streamlit/duckdb
  not installed in this venv): 1,003 passed, 4 skipped. The only failure is
  `test_real_corpus_ingests_with_zero_skips`, which needs the literature PDFs that live
  outside the repo; it fails identically on the commit before this work.
- `tests/fixtures/api_openapi.json` regenerated: the live API only added endpoints since the
  snapshot (`/jobs/{id}/mapping`, the `/lab/*` routes), none were removed.
- Frontend: `vitest` 18 files / 71+ tests, `tsc --noEmit`, `eslint` clean.
- Clean-environment build: the API and frontend Docker images are rebuilt from
  `requirements`/`package.json` on every deploy (`docker compose up -d --build`).
- Real-data reproduction: per-upload RUL on the cached XJTU-SY canonical features gives MAE
  22,283 s vs naive 32,456 s, identical to the within-domain row of
  `docs/cross-dataset-results.md`, so the upload path is the published experiment, not a
  new one.

## Scientific audit findings

1. **Leakage, per-upload RUL: none found.** Every bearing is predicted by a model fit
   without it (`experiments.run_split` asserts disjoint bearings and allowed roles); the
   conformal calibrator uses inner GroupKFold over the training bearings only; the
   applicability model is fit on the training bearings only. Test:
   `test_run_to_failure_upload_learns_and_tests_rul_on_its_own_bearings`.
2. **Pre-registration.** Model kind (`raw_seconds` ExtraTrees), the 3-bearing minimum, the
   gate (held-out MAE < naive MAE) and the reliability thresholds (0.7 / 0.4) were fixed in
   code before any upload or the real-data check was run; nothing was tuned on a result.
3. **Gate on test data (disclosed, not hidden).** Whether RUL trajectories are shown depends
   on the held-out result itself. The reported MAE is still an honest held-out number for
   that dataset, and it is shown whether or not the gate passes, so a failing dataset is
   visible, not filtered out. Across many uploads, the set of datasets *with* RUL shown is
   by construction the better-performing subset.
4. **Labels for custom uploads come from the user.** A custom bearing is run-to-failure only
   when the uploader says so; the last recording is then taken as the failure. A bearing
   declared failed whose last stage is still HEALTHY is flagged (`ends_healthy`).
5. **Interval coverage is empirical.** The 90% conformal ranges are reported with their
   measured coverage per dataset; no coverage guarantee is claimed (D28).
6. **Health reliability is label-free.** The trend uses only HI and elapsed time;
   prognosability is reported only when every bearing has an end-of-life label. The rating
   measures consistency of the HI, not its accuracy.
7. **Earlier "FEMTO HI discrepancy" was a misreading, not a defect.** Upload trajectories use
   the cross-domain amplitude HI (`experiments.ROUTING_HI`); its documented FEMTO trend is
   0.259 and the live value is 0.259 (XJTU 0.636 both). The 0.535 compared against earlier
   was the reference-HI row.
8. **LLM grounding is now checked, not only prompted.** `rag.explain.unsupported_numbers`
   rejects an online answer containing any number absent from the model result, the cited
   evidence or the question (within 0.5% or the answer's written precision, allowing
   s/min/h/day and fraction/percent conversions); the deterministic template is shown
   instead, with the reason. Limitation: a wrong number that happens to equal another
   supplied number is not caught.
9. **No fault-type claims.** Stages remain severity bands; the upload path adds no fault
   label. Unchanged: nothing refit on FEMTO `Full_Test_Set`; frozen FEMTO artifacts and the
   reference HI are loaded, never refit.
10. **Simplicity pass.** The upload RUL reuses `experiments.prepare/run_split/bearing_metrics`
    (one new 60-line module) instead of a second training path; `.mat`/`.wav` reading lives
    in `generic.read_generic_file`, so the adapter and the rest of the pipeline are
    unchanged.

## Known limits (stated on the site and in docs/upload-analysis.md)

- RUL needs >= 3 run-to-failure bearings in one upload; datasets without failures get health
  results only.
- MATLAB v7.3 (HDF5) files are rejected with a message; one folder per bearing and one file
  per recording is assumed.
- Retrieval misses one of 12 evaluation questions (the data-contract question retrieves the
  architecture doc); reported, not tuned away (artifacts/evidence/M7/).
