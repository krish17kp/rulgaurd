# Dataset Audit

Evidence-based, from direct file inspection on 2026-07-21. Bounded sampling used where noted (full 18GB college set is never read in one pass). Source paths come from `config/data_paths.toml`.

## College run-to-failure (`Vibration_Bearing_RuntoFailure`)

Path: `D:/capstone/data/Vibration_Bearing_RuntoFailure` (129 files; a second identical copy exists at `D:/capstone/data/data collection git/context/Vibration_Bearing_RuntoFailure`, also 129 files, unused by config).

Confirmed facts:
- 129 files, range `LogFile_2022-06-20-17-00-31.csv` to `LogFile_2022-06-26-01-00-31.csv` — matches `Description.txt`.
- No header. 4 comma-separated columns: vibration X, vibration Y, bearing temperature, ambient temperature.
- Row count: first file 2,000,001 rows, last file 2,000,001 rows (checked via `wc -l`). Stated ~2,000,000/file confirmed to within 1 row (trailing newline or 1 extra sample — not yet resolved, non-blocking).
- File size: ~143.5 MB (first file, on-disk stat) — consistent with 141-144MB/file quoted in `command.md`.
- Bearing temperature (col 3): first file ~41.6degC constant per-file value at start, last file ~100.4degC — **exceeds the stated 85degC stop threshold**, supporting temperature as the actual terminal trigger for this run.
- Ambient temperature (col 4): 24.8degC (first file) to 26.6degC (last file) — stable, plausible.
- Vibration X/Y (sampled every 200th row, NOT exhaustive max): first file |X|<=1.82, |Y|<=2.84; last file |X|<=5.83, |Y|<=6.43. Magnitude grows with degradation as expected. The stated "9 m/s^2" stop criterion is **not proven** by this sample (could be exceeded elsewhere, could use a different definition: RMS/peak/vector-magnitude/other axis/window). Treat as terminal-event evidence only, per `command.md` section 3.1 caveat — do not assume a specific definition in code.
- No malformed rows (col count != 4) detected in the sampled rows of the last file.

Open / unverified:
- Exact row-count discrepancy (2,000,001 vs stated ~2,000,000) not root-caused; likely a trailing blank-line artifact or the spec's "approximately" language. Adapter must handle it without assuming an exact count.
- Full duration-per-file check against the stated 78.125s (2,000,000 / 25,600 Hz) not done exhaustively; sampling is consistent with ~25.6kHz but exact rate not independently measured from timestamps (file has no timestamp column — only filename timestamps, one per file).

## FEMTO / PRONOSTIA

Paths (all under `D:/capstone/data/data collection git/context/femto dataset/`):
- `Training_set/Learning_set` (6 complete trajectories)
- `Test_set/Test_set` (11 censored prefixes)
- `Validation_Set/Full_Test_Set` (11 full continuations — frozen-model eval only, never fit anything on this)

### Acceleration file schema (confirmed, `Bearing1_1/acc_00001.csv`)
No header, 6 comma-separated columns: `hour, minute, second, microsecond, horizontal_accel, vertical_accel`. Row count: 2560 (confirmed exact). Matches spec.

### Temperature file schema (confirmed, `Bearing1_1/temp_00001.csv`)
No header, 5 comma-separated columns: `hour, minute, second, ?, temperature` (Bearing1_1 sample). `command.md` warns some bearings may use semicolon: confirmed present in `data/fixtures/femto/Bearing2_1/temp_00001.csv` (also present in Bearing3_1, Bearing1_2 per fixture README). Adapter must auto-detect delimiter, not assume comma.

### Per-bearing file counts — independently recounted, matches `command.md` checkpoint tables exactly (all 28 rows, Learning_set / Test_set / Full_Test_Set)

| Bearing | Learning acc/temp | Test-prefix acc/temp | Full-test acc/temp |
|---|---|---|---|
| Bearing1_1 | 2803 / 466 | - | - |
| Bearing1_2 | 871 / 144 | - | - |
| Bearing1_3 | - | 1802 / 0 | 2375 / 0 |
| Bearing1_4 | - | 1139 / 188 | 1428 / 237 |
| Bearing1_5 | - | 2302 / 383 | 2463 / 410 |
| Bearing1_6 | - | 2302 / 383 | 2448 / 408 |
| Bearing1_7 | - | 1502 / 250 | 2259 / 376 |
| Bearing2_1 | 911 / 151 | - | - |
| Bearing2_2 | 797 / 0 | - | - |
| Bearing2_3 | - | 1202 / 0 | 1955 / 0 |
| Bearing2_4 | - | 612 / 101 | 751 / 125 |
| Bearing2_5 | - | 2002 / 335 | 2311 / 386 |
| Bearing2_6 | - | 572 / 0 | 701 / 116 |
| Bearing2_7 | - | 172 / 28 | 230 / 38 |
| Bearing3_1 | 515 / 89 | - | - |
| Bearing3_2 | 1637 / 0 | - | - |
| Bearing3_3 | - | 352 / 58 | 434 / 72 |

Note vs. `command.md`'s "Test_set.7z" counts (a slightly different table listed under "Censored test-prefix checkpoints" with lower numbers, e.g. Bearing1_3=1802): our recount of `Test_set/Test_set` matches that lower "censored" table exactly, and `Validation_Set/Full_Test_Set` matches the higher "Full-test archive checkpoints" table exactly. The two tables in `command.md` are for the two different archives, not conflicting — resolved.

### Hidden RUL, independently recomputed and verified exact match

`RUL_seconds = (Full_Test_Set acc count - Test_set acc count) * 10s` (one acquisition per 10s):

| Bearing | Computed RUL (s) | command.md expected | Match |
|---|---|---|---|
| Bearing1_3 | 573*10=5730 | 5730 | Y |
| Bearing1_4 | 289*10=2890 | 2890 | Y |
| Bearing1_5 | 161*10=1610 | 1610 | Y |
| Bearing1_6 | 146*10=1460 | 1460 | Y |
| Bearing1_7 | 757*10=7570 | 7570 | Y |
| Bearing2_3 | 753*10=7530 | 7530 | Y |
| Bearing2_4 | 139*10=1390 | 1390 | Y |
| Bearing2_5 | 309*10=3090 | 3090 | Y |
| Bearing2_6 | 129*10=1290 | 1290 | Y |
| Bearing2_7 | 58*10=580 | 580 | Y |
| Bearing3_3 | 82*10=820 | 820 | Y |

All 11 match exactly. M1 acceptance criterion "hidden-RUL derivation independently reproduced" is satisfied.

## data collection git repo's own copy (not used by pipeline)

`D:/capstone/data/data collection git/Vibration_Bearing_RuntoFailure/` — `git status` shows all 129 files as locally deleted (working tree), while `git lfs ls-files` still lists 129 tracked objects. Files are not on disk here (LFS content never checked out / removed to free space). Not a data-loss event: two other full copies exist (see above) and config does not point here. Left untouched; no `git lfs pull`/checkout run (would need ~18GB, only 42GB free on D:).

## New finding: literal NaN sensor dropouts in college CSVs (confirmed 2026-07-21, via M1 adapter code against real files)

The first file (`LogFile_2022-06-20-17-00-31.csv`) contains rows where fields are the literal string `NaN` (not empty, not malformed - the row still has exactly 4 comma-separated fields):
- 82 rows with `NaN` in the bearing-temperature column (col 3) — occurring in two clusters (~41 rows each) at approximately row 72,043 and row 1,608,122.
- Separately, 40 consecutive rows (~row 1,388,129-1,388,168) with `NaN` in **both vibration columns** (col 1, col 2) while temperature stays valid — a distinct dropout event from the temperature gaps.
- Middle file (`LogFile_2022-06-23-09-01-31.csv`) also has 82 temp-NaN rows; last file has 41.

This means missing-value handling is not FEMTO-only: the college adapter (`college.py`) must preserve `NaN` per-column, per-row rather than raising or fabricating a fill value. `read_college_chunks` was corrected to do this (previously raised on any NaN, which is wrong — these are genuine sensor dropouts, not malformed data).

**Full-dataset scan (all 129 files, 258,000,129 rows, bounded-memory chunked read via `college.py`, ~5min runtime — `artifacts/evidence/REVIEW-M1/college_nan_scan.txt`):**
- **129/129 files** (100%) contain at least one temperature NaN. Total temp-NaN cells: 21,074 across both temperature columns (~82 rows/file average, consistent with the 3-file sample).
- **129/129 files** (100%) contain at least one vibration NaN. Total vibration-NaN cells: 12,800 across both vibration columns (~50 rows/file average).
- This is a systemic, recurring sensor-logging artifact across the entire run, not a rare edge case — M2 feature extraction must budget for it in every window, not treat it as an exceptional path.

Implication for M2: window-level features must carry an explicit missing-sample count/flag per column, matching the FEMTO `temp_available` pattern in `docs/data-contract.md` — the contract's current `temp_available: bool` (file-level) is too coarse for college data and should become row/window-level coverage, not just presence. Flagged as a data-contract follow-up, not fixed in this M1 pass (documentation-only change, deferred to M2 when features.py is written and can decide the exact representation).

## Processing-cost estimate

College: 129 files x ~143.5MB = ~18.5GB raw, 2M rows/file. Feature extraction at the 25,600-sample/50%-overlap default yields ~78 windows/file (2,000,000/12,800 - 1) x 129 files = ~10,000 feature rows total (tiny — kilobytes as Parquet). Never materialize raw windows to disk.

FEMTO: acceleration files are already bounded (2560 rows, ~2560*6*8bytes~123KB each); one feature row per acquisition. Total acquisitions across Learning_set: 2803+871+911+797+515+1637 = 7534 feature rows for the six training bearings.
