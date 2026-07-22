# REVIEW-M1 evidence

Date: 2026-07-21. Task IDs M1-T1, M1-T2, M1-T3.

## Code delivered
- `src/bearing_pdm/config.py` — loads `config/data_paths.toml` (stdlib `tomllib`, no new dependency).
- `src/bearing_pdm/college.py` — file discovery, filename-timestamp parsing, chronological ordering, header detection, bounded-memory chunked reads (4-col, NaN-tolerant).
- `src/bearing_pdm/femto.py` — bearing/role discovery, acquisition listing, acc (6-col) + temp (5-col, comma/semicolon auto-detect) parsing, nearest-wall-clock temperature alignment.
- `tests/test_college.py`, `tests/test_femto.py` — 25 tests against committed fixtures (`data/fixtures/`).

## Test results
```
pytest -q -> 25 passed
ruff check . -> All checks passed
```

## Real-data verification (beyond fixtures)
Ran both adapters against the actual local archives referenced by `config/data_paths.toml` (not committed — private local paths):
- College: discovered all 129 real files, chronologically ordered correctly. Chunked-read the real first and last file in full (2,000,001 rows each) with a 200k-row chunk cap — confirms bounded memory on real file sizes, ~1s/file.
- FEMTO: discovered all 6 learning + 11 test-censored + 11 full-test bearing folders. Recounted acc/temp file counts for all 28 archive entries via adapter code — **matches `docs/dataset-audit.md` / `command.md` exactly**. Recomputed all 11 hidden `Full_Test_Set` RUL values via adapter code — **11/11 match `command.md` exactly**.
- Full-dataset NaN scan (all 129 college files, 258,000,129 rows) — see `college_nan_scan.txt`. Found a real data-quality fact not in any prior spec: every one of the 129 files contains literal-`NaN` sensor dropouts in both temperature (21,074 cells) and vibration (12,800 cells) columns. Fixed `college.py` to preserve these explicitly instead of raising (was initially too strict — treated NaN as malformed data). See `docs/decisions.md` D6.

## M1 acceptance criteria (docs/milestone.md)
- Bounded-memory chunked reads: yes, verified on real 143MB files (200k-row cap, ~1s/file).
- Schema/delimiter auto-detection: yes (college header detection; FEMTO comma/semicolon).
- Chronological ordering from filenames/timestamps: yes, tested + verified on real 129-file set.
- Missing temperature stays explicit: yes for FEMTO (file-level `temp_available` via `find_nearest_temperature_index` returning `None`); for college, upgraded to NaN-per-cell after the real-data finding above (data-contract follow-up noted in `docs/decisions.md` D6, not yet applied — deferred to M2).
- Hidden-RUL derivation independently reproduced: yes, both by shell recount (M0) and now by adapter code (M1), 11/11 match.

## Verdict
M1 gate met. Proceeding to M2 (feature pipeline).
