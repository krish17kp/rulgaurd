# Fixtures

Tiny real-data excerpts committed for tests. Never the full datasets.

## femto/Bearing1_1/
- `acc_00001.csv`, `acc_00002.csv`: real, complete acceleration acquisitions (2560 rows, 6 cols, comma-delimited, no header).
- `temp_00001.csv`: real, complete temperature file (600 rows, 5 cols, comma-delimited).

## femto/Bearing2_1/
- `temp_00001.csv`: real temperature file using the **semicolon**-delimited variant (confirmed present in Bearing2_1, Bearing3_1, Bearing1_2 of the actual archive).

## college/
- `LogFile_2022-06-20-17-00-31_head5000.csv`: first 5000 rows of the real first hourly file (`head -n 5000`), no header, 4 cols.
- `LogFile_2022-06-26-01-00-31_tail5000.csv`: last 5000 rows of the real final hourly file (`tail -n 5000`) - bearing temperature column here exceeds 85 degC, confirming the stop-criterion evidence.

Source: `config/data_paths.toml` -> `college.raw_dir` / `femto.training_dir` (gitignored, local machine paths).
