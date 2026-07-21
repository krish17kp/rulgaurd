# Decisions and conflict resolutions

Ordered by source-priority: (1) raw files/inspection, (2) official dataset docs, (3) `Description.txt`, (4) primary papers, (5) literature review, (6) original prompt.

## D1: `command.md` two FEMTO checkpoint tables (2026-07-21)
`command.md` section 3.2 lists "Full-test archive checkpoints" and "Censored test-prefix checkpoints" as separate tables with different counts for the same bearing IDs (e.g. Bearing1_3: 2375 vs 1802). Initial read could look contradictory.
Resolution: they describe two different archives (`Validation_Set/Full_Test_Set` vs `Test_set/Test_set`), not a conflict. Confirmed by direct recount (`docs/dataset-audit.md`) — both tables match their respective archive exactly, and the difference reproduces the hidden RUL table exactly (11/11 match). No correction needed to source data; documentation-only clarification.

## D2: college row count "approximately 2,000,000" vs measured 2,000,001 (2026-07-21)
`Description.txt`/`command.md` state ~2,000,000 rows/file at 25.6kHz for 78.125s. Measured (first + last file): 2,000,001 rows.
Resolution: treat as "approximately" language being accurate to within 1 row; do not hard-code an exact expected row count in the adapter. Config-driven window size (25,600 samples, 50% overlap) remains the default per `command.md` section 4.4 — not changed.

## D3: college "9 m/s^2" stop criterion — definition unverified (2026-07-21)
`command.md` explicitly forbids assuming RMS/peak/vector-magnitude without proof. Sampled inspection of the final file (every-200th-row) shows |X|<=5.83, |Y|<=6.43 m/s^2 — under 9, but sampling is not exhaustive and cannot confirm or refute the threshold or its definition.
Resolution: per instruction, treat "vibration above 9 m/s^2" only as terminal-event context, not as a label-generation rule. The bearing-temperature stop criterion (85degC) IS independently confirmed (last file reaches ~100.4degC), so temperature is documented as the verified terminal trigger for this run; vibration threshold remains an open/unverified fact, recorded here rather than guessed at in code.

## D4: duplicate data copies found (2026-07-21)
Three copies of the 129 college CSVs exist on disk: (a) `D:/capstone/data/Vibration_Bearing_RuntoFailure` [used by config], (b) `D:/capstone/data/data collection git/context/Vibration_Bearing_RuntoFailure` [unused], (c) the `data collection git` repo's own tracked copy, currently missing from its working tree (LFS objects not checked out, 129 files show as deleted in `git status` but are still tracked in `git lfs ls-files`).
Resolution: per the no-delete rule, none of these are touched. Config points only at (a). (b) and (c)'s state are documented, not resolved — user's call whether to deduplicate.

## D5: app-repo `context/` folder populated with copied source files (2026-07-21, found during recovery, not caused by this session)
An earlier session copied several PDFs, the literature review docx, and `Description.txt` into `D:/capstone/bearing-rul-predictive-maintenance/context/`, contradicting the "don't copy source files into the app repo" instruction.
Resolution: left in place (no delete authority). Confirmed harmless — correctly covered by `.gitignore` (`context/`), never staged, small (~8MB, no bulk CSV data copied in). Flagged to user in the recovery report; not auto-removed.
