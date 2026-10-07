"""Generate deploy_data/college_trajectory.json: whole-run feature/temperature trends
and chronological walk-forward RUL for the college case study (Phase I).

College is ONE continuous run-to-failure trajectory spread across 129 LogFile_*.csv
files - never 129 separate bearings. This script does not re-read the ~18GB raw
dataset; it reuses the already-computed, already-committed per-acquisition feature
parquet (data/processed/college_*.parquet, built via build_features.py --dataset
college) and the committed walk-forward predictions (deploy_data/rul_predictions.parquet,
deploy_data/rul_evaluation.json). No model is fit here.

D11 (docs/decisions.md): a FEMTO-fit Health Indicator must not be applied to college's
feature scale. This artifact intentionally carries no reference_hi/stage fields.
D10: college's naive MAE=0.0 is an algebraic oracle identity, not a real baseline -
the caveat string is carried through verbatim from rul_evaluation.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bearing_pdm.config import load_data_paths
from bearing_pdm.storage import get_connection, latest_batch_parquet

REPO_ROOT = Path(__file__).resolve().parents[1]
BEARING_RUN_ID = "college:nsk6205"

TREND_COLUMNS = [
    "vibration_x_rms",
    "vibration_x_kurtosis",
    "vibration_x_crest_factor",
    "vibration_x_dominant_frequency_hz",
    "vibration_x_spectral_centroid_hz",
    "vibration_x_spectral_entropy",
    "vibration_x_total_spectral_energy",
    "vibration_y_rms",
    "vibration_y_kurtosis",
    "vibration_y_crest_factor",
    "bearing_temp_mean",
    "ambient_temp_mean",
    "bearing_minus_ambient_temp_mean",
]


def _find_college_parquet(config_path: str = "config/data_paths.toml") -> Path:
    """The DuckDB-registered newest college batch (storage.latest_batch_parquet)
    - NOT a filename glob+sort: college_*.parquet names are uuid4, so sorting
    them is arbitrary and can silently pick a stale, partial-coverage batch
    over a newer, fuller one (or vice versa)."""
    paths = load_data_paths(config_path)
    con = get_connection(paths.duckdb_path, read_only=True)
    try:
        path = latest_batch_parquet(con, "college", role="college_run")
    finally:
        con.close()
    if path is None or not path.is_file():
        raise SystemExit(
            "No registered college feature batch found. Run "
            "scripts/build_features.py --dataset college first."
        )
    return path


def main() -> None:
    features = pd.read_parquet(_find_college_parquet())
    features = features[features["bearing_run_id"] == BEARING_RUN_ID].sort_values("sequence_index")
    if features.empty:
        raise SystemExit(f"No rows for {BEARING_RUN_ID} in the college feature parquet.")

    n_source_files = features["source_file_path"].nunique()
    n_raw_college_files = len(list((REPO_ROOT / "datasets/college").glob("LogFile_*.csv")))
    eval_json = json.loads((REPO_ROOT / "deploy_data/rul_evaluation.json").read_text())

    predictions = pd.read_parquet(REPO_ROOT / "deploy_data/rul_predictions.parquet")
    college_pred = predictions[
        (predictions["dataset_id"] == "college") & (predictions["model"] == "extra_trees")
    ].sort_values("sequence_index")

    trend = {
        col: [round(float(v), 4) if pd.notna(v) else None for v in features[col]]
        for col in TREND_COLUMNS
        if col in features.columns
    }

    out = {
        BEARING_RUN_ID: {
            "dataset_id": "college",
            "n_source_files_in_cache": int(n_source_files),
            "n_raw_college_files_on_disk": int(n_raw_college_files) or None,
            "coverage_note": (
                f"Full coverage: all {n_raw_college_files} raw LogFile_*.csv files are "
                "represented in this cache (built with --sample-stride 1)."
                if n_raw_college_files and n_source_files >= n_raw_college_files else
                f"The cached feature parquet covers {n_source_files}/{n_raw_college_files or '?'} "
                "raw LogFile_*.csv files - built with a --sample-stride > 1 representative "
                "sample, not every file. This is a sampling stride, not missing/dropped data."
            ),
            "n_acquisitions": int(len(features)),
            "sample_rate_hz": float(features["sample_rate_hz"].iloc[0]),
            "sequence_index": features["sequence_index"].astype(int).tolist(),
            "event_timestamp": [str(t) for t in features["event_timestamp"]],
            "temp_available_fraction": round(float(features["temp_available"].mean()), 4),
            "feature_trends": trend,
            "actual_rul_seconds": [
                round(float(v), 1) if pd.notna(v) else None for v in features["rul_seconds"]
            ],
            "held_out_predicted_rul_seconds": {
                "sequence_index": college_pred["sequence_index"].astype(int).tolist(),
                "predicted_rul_seconds": [
                    round(float(v), 1) for v in college_pred["predicted_rul_seconds"]
                ],
            },
            "walk_forward_overall": eval_json["college_overall_by_model"],
            "naive_caveat": eval_json["college_naive_caveat"],
            "domain_shift_note": (
                "FEMTO-fit models (reference HI, RUL) are not applied to college data "
                "here; college is evaluated only with its own chronological "
                "walk-forward split (D11, docs/decisions.md)."
            ),
        }
    }

    out_path = REPO_ROOT / "deploy_data" / "college_trajectory.json"
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KiB, {len(features)} acquisitions, {n_source_files} files)")


if __name__ == "__main__":
    main()
