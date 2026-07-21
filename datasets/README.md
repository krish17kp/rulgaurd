# Datasets

Two independent bearing vibration datasets, kept in separate folders and
never mixed at the raw-file level (see `docs/data-contract.md` in the
application code for how they're normalized into a shared feature schema
downstream).

## `college/`
129 hourly `LogFile_*.csv` files (no header, 4 columns: vibration X,
vibration Y, bearing temperature, ambient temperature) from a single NSK
6205 ball-bearing run-to-failure test, ~128 hours, 25.6kHz sampling.
Tracked via Git LFS (real per-hour files, ~143MB each, ~18GB total).
See `context/Description.txt` (local, not published - see repo root
`.gitignore`) for full acquisition conditions, or `docs/dataset-audit.md`
for independently-verified facts (schema, row counts, confirmed stop
criterion, sensor-dropout characteristics).

## `femto/`
Raw archives for the FEMTO-ST / PRONOSTIA IEEE PHM 2012 Prognostic
Challenge dataset (`Training_set.zip`, `Test_set.zip`, `Validation_Set.zip`).
Tracked via Git LFS (~1.1GB total). These are the original challenge
archives - extract locally to get the per-bearing `acc_NNNNN.csv` /
`temp_NNNNN.csv` acquisition files the application code reads (see
`docs/dataset-audit.md` for confirmed per-bearing file counts and the
independently-recomputed hidden `Validation_Set` RUL values).

Source: https://github.com/wkzs111/phm-ieee-2012-data-challenge-dataset
(IEEE PHM 2012 Prognostic Challenge). `Validation_Set.zip` contains the
full continuation of the 11 censored `Test_set` bearings - never use it
to fit anything; it exists only to score a frozen model (see
`docs/data-contract.md`).
