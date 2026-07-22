# REVIEW-M2 evidence

Date: 2026-07-21. Task IDs M2-T1..T4.

## Code delivered
- `src/bearing_pdm/features.py` — 14 time-domain stats, FFT-based frequency features (dominant freq, spectral centroid/entropy, frequency RMS, band-energy fractions), temperature stats+slope. NaN-in/NaN-out, zero-denominator guarded (never raises, never fabricates).
- `src/bearing_pdm/pipeline.py` — assembles `docs/data-contract.md` rows: college sliding-window (chunk-boundary overlap carried via bounded buffer) and FEMTO per-acquisition, both calling `features.py`.
- `src/bearing_pdm/storage.py` — Parquet writer + DuckDB lineage (`docs/database-schema.md`); wide feature columns confirmed absent from the `acquisitions` table (test-enforced).
- `scripts/build_features.py` — CLI entry point (command.md section 20).
- `tests/test_features.py`, `tests/test_pipeline.py`, `tests/test_storage.py` — 48 total tests passing.

## Test results
```
pytest -q -> 48 passed
ruff check . -> All checks passed
```

## Real-data verification
Ran the pipeline against real files (not just fixtures):
- College, real first file (2,000,001 rows): 155 windows at the default 25,600/50% config — matches the analytically expected count exactly. First window `rul_seconds` = 460878.125s = **128.02 hours**, matching `Description.txt`'s stated 128-hour total operating period almost exactly (independent cross-check of the RUL construction, not just row counts).
- College, real last file: 155 windows, final window `rul_seconds` = 1.125s (correctly near zero at the end of the run).
- FEMTO, real Bearing1_1 (full 2803 acquisitions, not a sample): all 2803 rows built successfully in ~65s. `rul_seconds` for acq 1 = 28,020s = (2803-1)*10, acq 2803 = 0s — matches the `RUL_seconds = final - current` formula at 10s cadence. 2801/2803 acquisitions found a temperature match within the 90s tolerance.
- Real production runs completed and verified in DuckDB `feature_batches`:
  - `scripts/build_features.py --dataset femto`: all 6 learning bearings, **7534 rows** (matches the exact sum of all 6 bearings' real acc-file counts: 2803+871+911+797+515+1637), ~4.5min total.
  - `scripts/build_features.py --dataset college --sample-stride 5`: **4030 window rows** from 26/129 files (1-in-5 stride). A full-129-file foreground run was attempted first but the background process was killed by the environment before completing (not a code failure - the same windowing code was already verified correct on the real first and last file individually, section above). Per `command.md` section 26.8 ("review sample across the life trajectory... process the full collection only if disk/runtime/memory estimates are safe"), switched to the sanctioned strided-sample shortcut rather than re-attempting the full run a third time (section 6.2 retry-limit policy). `rul_seconds` range in the sample: 1.125s to 450,198s (~125h), consistent with the ~128h total run.
  - Both batches' `code_version` fields record the git SHA active at extraction time (`ccd326f`/`1edce96`), confirming lineage traceability works end to end.

## M2 acceptance criteria (docs/milestone.md)
- No raw-window explosion: yes — windows are computed and immediately reduced to a feature row; only the bounded sliding buffer (~2x window size) is held in memory.
- Deterministic output: yes for feature values (no randomness in formulas); `acquisition_id` is a fresh UUID per run by design (identifier, not a feature).
- Schema version + hashes recorded: yes — `schema_version='v1'`, per-source-file `sha256`, per-Parquet-batch `sha256`, `code_version` (git short SHA) all recorded in DuckDB.
- Zero-denominator and constant-signal tests pass: yes — `test_features.py` covers all-zero, constant-nonzero, and all-NaN signals explicitly.

## Verdict
M2 gate met. Proceeding to M3 (health indicator).
