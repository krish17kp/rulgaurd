# REVIEW-M0 evidence

Date: 2026-07-21

## Recovery audit
- App repo: D:/capstone/bearing-rul-predictive-maintenance (pre-existing, no commits).
- Source data confirmed present, untouched: college CSVs (D:/capstone/data/Vibration_Bearing_RuntoFailure, 129 files), FEMTO (D:/capstone/data/data collection git/context/femto dataset/{Training_set,Test_set,Validation_Set}).
- data-collection-git repo's own CSV copy missing from working tree (LFS not checked out) — not used by pipeline, not touched.
- No destructive command run. Read-only inspection only (ls, wc -l, head/tail, awk sampling, git status/lfs ls-files/check-ignore).

## Dataset audit highlights (full detail: docs/dataset-audit.md)
- College: no-header 4-col CSV confirmed, 2,000,001 rows/file, bearing temp 41.6C->100.4C (exceeds 85C stop threshold - confirmed terminal trigger). Vibration 9 m/s^2 criterion NOT independently confirmed (sampled only) - documented as open per command.md instruction not to assume.
- FEMTO: acc file 6-col/2560-row confirmed. temp file 5-col comma-delimited confirmed (semicolon variant not observed in sample). All 28 per-bearing file counts across Learning_set/Test_set/Full_Test_Set recounted and match command.md exactly. All 11 hidden-RUL values recomputed from (Full_Test_Set - Test_set) acc-file-count * 10s and match command.md exactly (11/11).

## Commands run
ls, wc -l, head, tail, awk (sampling), git status --short, git lfs ls-files, git lfs version, git check-ignore -v, python --version, df -h

## Verdict
M0 acceptance criteria met: datasets separated, archive roles confirmed against real files (not assumed), no hidden-test leakage designed in, raw rows not planned for DuckDB (see docs/database-structure.md, pre-existing). Ready for M1.
