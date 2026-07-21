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
- A real production run of `scripts/build_features.py --dataset femto` (all 6 learning bearings, full row counts) and `--dataset college` (all 129 files) was executed after this evidence file was written — see `docs/dataset-audit.md` / DuckDB `feature_batches` table for the resulting batch IDs once complete (long-running, tracked separately, not blocking this evidence).

## M2 acceptance criteria (docs/milestone.md)
- No raw-window explosion: yes — windows are computed and immediately reduced to a feature row; only the bounded sliding buffer (~2x window size) is held in memory.
- Deterministic output: yes for feature values (no randomness in formulas); `acquisition_id` is a fresh UUID per run by design (identifier, not a feature).
- Schema version + hashes recorded: yes — `schema_version='v1'`, per-source-file `sha256`, per-Parquet-batch `sha256`, `code_version` (git short SHA) all recorded in DuckDB.
- Zero-denominator and constant-signal tests pass: yes — `test_features.py` covers all-zero, constant-nonzero, and all-NaN signals explicitly.

## Verdict
M2 gate met. Proceeding to M3 (health indicator).
