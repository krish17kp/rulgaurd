#!/usr/bin/env python
"""Export the smallest tracked bundle that lets the existing dashboard run on
Streamlit Community Cloud, which clones the repo fresh and therefore has none
of the gitignored local artifacts (config/data_paths.toml, data/processed/,
artifacts/models/, reports/metrics/).

Everything written here is a real output of the existing pipeline - feature
rows, measured waveforms, fitted models and metric files are copied, never
recomputed or synthesised. The bundle is a representative SUBSET, not the full
datasets: three FEMTO bearings (one per operating condition) with their whole
feature history, plus a few genuinely measured raw windows per bearing.

Deliberately NOT bundled: artifacts/models/rul_extra_trees.joblib is ~104MB,
over GitHub's 100MB hard limit. Cloud mode reads that model's leave-one-
bearing-out predictions from rul_predictions.parquet instead - already
out-of-sample, and 216KB.

Usage:
    PYTHONPATH=src python scripts/build_deploy_snapshot.py --config config/data_paths.toml
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from bearing_pdm.config import load_data_paths, resolve_stored_path
from bearing_pdm.storage import get_connection, latest_batch_parquet

DEPLOY_DIR = Path("deploy_data")

# One bearing per FEMTO operating condition. Their whole feature history ships,
# so the Health Indicator curve and the RUL trajectory are real full-life plots.
SNAPSHOT_BEARINGS = ("femto:Bearing1_1", "femto:Bearing2_1", "femto:Bearing3_1")

# Life fractions sampled for raw waveforms: healthy, mid-life, late/degrading.
RAW_LIFE_FRACTIONS = (0.05, 0.50, 0.95)

COPY_ARTIFACTS = [
    ("artifacts/models/reference_hi_model.joblib", True),
    ("artifacts/models/stage_thresholds.joblib", True),
    ("artifacts/models/transparent_hi_baseline.joblib", True),
    ("artifacts/models/pca_hi_model.joblib", True),
    ("artifacts/models/rul_naive.joblib", True),
    ("artifacts/models/rul_selected_model.json", True),
    ("reports/metrics/rul_evaluation.json", True),
    ("reports/metrics/health_indicator_comparison.json", True),
    ("reports/metrics/rul_predictions.parquet", True),
    ("reports/metrics/hidden_set_evaluation.json", False),  # optional
]

_SEARCH_ROOTS: tuple[Path, ...] = ()


def _raw_femto(row: pd.Series) -> dict:
    from bearing_pdm.femto import (
        build_temperature_time_index,
        find_nearest_temperature_index,
        read_acceleration,
        read_temperature,
    )

    source = resolve_stored_path(row["source_file_path"], _SEARCH_ROOTS)
    bearing_dir = source.parent
    acc_index = int(source.stem.split("_")[1])
    acc = read_acceleration(bearing_dir, acc_index)
    temp = None
    if bool(row["temp_available"]):
        idx = find_nearest_temperature_index(
            bearing_dir, acc_index, build_temperature_time_index(bearing_dir)
        )
        if idx is not None:
            temp = read_temperature(bearing_dir, idx)["temperature_c"].to_numpy()
    return {
        "vibration_x": acc["accel_horizontal"].to_numpy(),
        "vibration_y": acc["accel_vertical"].to_numpy(),
        "temperature_c": temp,
    }


def _raw_college(row: pd.Series) -> dict:
    from bearing_pdm.college import COLLEGE_COLUMNS

    skiprows = int(row["row_start"])
    nrows = int(row["row_end"]) - int(row["row_start"]) + 1
    window = pd.read_csv(
        resolve_stored_path(row["source_file_path"], _SEARCH_ROOTS),
        header=None, names=COLLEGE_COLUMNS, skiprows=skiprows, nrows=nrows,
    )
    return {
        "vibration_x": window["vibration_x"].to_numpy(),
        "vibration_y": window["vibration_y"].to_numpy(),
        "temperature_c": window["bearing_temp_c"].to_numpy(),
    }


def _assert_no_host_paths(df: pd.DataFrame) -> None:
    """Refuse to write a bundle carrying this machine's directory layout into a
    public repository (.claude/rules/security.md)."""
    markers = ("/mnt/", "/home/", "D:/", "D:\\", "C:/", "C:\\")
    for column in df.select_dtypes("object").columns:
        values = df[column].astype(str)
        for marker in markers:
            hits = values[values.str.contains(marker, regex=False, na=False)]
            if not hits.empty:
                raise RuntimeError(
                    f"Refusing to export: column {column!r} contains host path "
                    f"marker {marker!r} (e.g. {hits.iloc[0]!r})"
                )


def _pick_rows(group: pd.DataFrame) -> pd.DataFrame:
    """Healthy / mid-life / late acquisitions, by position in the bearing's own
    record. Late matters most: FEMTO degradation is flat-then-cliff."""
    group = group.sort_values("sequence_index").reset_index(drop=True)
    picks = sorted({min(int(f * (len(group) - 1)), len(group) - 1) for f in RAW_LIFE_FRACTIONS})
    return group.iloc[picks]


def main() -> int:
    global _SEARCH_ROOTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    paths = load_data_paths(args.config)
    _SEARCH_ROOTS = paths.source_search_roots()

    con = get_connection(paths.duckdb_path)
    try:
        femto_path = latest_batch_parquet(con, "femto", role="learning")
        college_path = latest_batch_parquet(con, "college", role="college_run")
    finally:
        con.close()
    if femto_path is None:
        raise RuntimeError("No FEMTO learning batch - run scripts/build_features.py first.")

    DEPLOY_DIR.mkdir(exist_ok=True)

    # --- feature rows -----------------------------------------------------
    femto = pd.read_parquet(femto_path)
    femto = femto[
        (femto["role"] == "learning") & (femto["bearing_run_id"].isin(SNAPSHOT_BEARINGS))
    ].reset_index(drop=True)

    raw_source_rows = [_pick_rows(g) for _, g in femto.groupby("bearing_run_id")]

    college = pd.DataFrame()
    if college_path is not None:
        college_all = pd.read_parquet(college_path)
        # College's HI and RUL views are gated out of domain (D11), so only the
        # rows whose waveforms ship are needed to drive Signal & FFT.
        college = _pick_rows(college_all).reset_index(drop=True)
        raw_source_rows.append(college)

    snapshot = pd.concat([femto, college], ignore_index=True)
    # The recorded source paths are absolute paths on the machine that built the
    # batch (e.g. a D:\... Windows path from before the Linux migration). This
    # bundle is committed to a PUBLIC repository and cloud mode never resolves a
    # local file, so keep only the basename as provenance.
    snapshot["source_file_path"] = (
        snapshot["source_file_path"].astype(str).str.replace("\\", "/", regex=False).str.rsplit("/", n=1).str[-1]
    )
    _assert_no_host_paths(snapshot)
    snapshot.to_parquet(DEPLOY_DIR / "feature_snapshot.parquet", index=False)
    print(f"feature_snapshot.parquet: {len(snapshot)} rows "
          f"({len(femto)} femto / {len(college)} college)")

    # --- raw measured waveforms ------------------------------------------
    records = []
    for _, series in pd.concat(raw_source_rows, ignore_index=True).iterrows():
        raw = _raw_femto(series) if series["dataset_id"] == "femto" else _raw_college(series)
        records.append({
            "dataset_id": series["dataset_id"],
            "bearing_run_id": series["bearing_run_id"],
            "sequence_index": int(series["sequence_index"]),
            "sample_rate_hz": float(series["sample_rate_hz"]),
            "vibration_x": np.asarray(raw["vibration_x"], dtype="float32"),
            "vibration_y": np.asarray(raw["vibration_y"], dtype="float32"),
            "temperature_c": (
                None if raw["temperature_c"] is None
                else np.asarray(raw["temperature_c"], dtype="float32")
            ),
        })
    raw_df = pd.DataFrame(records)
    raw_df.to_parquet(DEPLOY_DIR / "raw_signal_samples.parquet", index=False)
    print(f"raw_signal_samples.parquet: {len(raw_df)} measured windows "
          f"({sorted(raw_df['dataset_id'].unique())})")

    # --- copy the small fitted models and metric files --------------------
    for rel, required in COPY_ARTIFACTS:
        src = Path(rel)
        if not src.exists():
            if required:
                raise RuntimeError(f"Missing {rel} - run the pipeline scripts first.")
            print(f"  (skipped optional {rel})")
            continue
        shutil.copy2(src, DEPLOY_DIR / src.name)
        print(f"  copied {rel}")

    total = sum(f.stat().st_size for f in DEPLOY_DIR.rglob("*") if f.is_file())
    print(f"\ndeploy_data total: {total/1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
