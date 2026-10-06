"""Generate deploy_data/trajectory_data.json for the web dashboard's bearing-trajectory
explorer. Ports the existing Streamlit HI/RUL trajectory views (dashboard.py's
"Health Indicator" and "RUL Prediction" views) into a compact artifact for the
Next.js frontend. Uses only existing fitted artifacts and the real leave-one-bearing-out
predictions already committed under deploy_data/ - no retraining, no fabricated values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bearing_pdm.health import apply_pca_hi, apply_reference_hi, apply_transparent_hi
from bearing_pdm.stages import assign_stages

REPO_ROOT = Path(__file__).resolve().parents[1]
LEARNING_BEARINGS = [
    "femto:Bearing1_1",
    "femto:Bearing1_2",
    "femto:Bearing2_1",
    "femto:Bearing2_2",
    "femto:Bearing3_1",
    "femto:Bearing3_2",
]


def _load_joblib(path: Path):
    import joblib

    return joblib.load(path) if path.exists() else None


def main() -> None:
    features = pd.read_parquet(REPO_ROOT / "data/processed/canonical_femto_learning.parquet")
    lobo = pd.read_parquet(REPO_ROOT / "deploy_data/rul_predictions.parquet")
    lobo_tree = lobo[lobo["model"] == "extra_trees"]
    eval_json = json.loads((REPO_ROOT / "deploy_data/rul_evaluation.json").read_text())
    lobo_eval = {r["held_out_bearing"]: r for r in eval_json["femto_lobo"] if r["model"] == "extra_trees"}

    reference_model = _load_joblib(REPO_ROOT / "deploy_data/reference_hi_model.joblib")
    baseline = _load_joblib(REPO_ROOT / "deploy_data/transparent_hi_baseline.joblib")
    pca_model = _load_joblib(REPO_ROOT / "deploy_data/pca_hi_model.joblib")
    thresholds = _load_joblib(REPO_ROOT / "deploy_data/stage_thresholds.joblib")
    if reference_model is None or thresholds is None:
        raise SystemExit("Missing reference_hi_model.joblib / stage_thresholds.joblib under deploy_data/")

    out: dict[str, dict] = {}
    for bearing_run_id in LEARNING_BEARINGS:
        df_bearing = (
            features[features["bearing_run_id"] == bearing_run_id]
            .sort_values("sequence_index")
            .reset_index(drop=True)
        )
        if df_bearing.empty:
            continue

        hi = apply_reference_hi(df_bearing, reference_model)
        stage = assign_stages(df_bearing, hi, thresholds)
        transparent_hi = apply_transparent_hi(df_bearing, baseline) if baseline is not None else None
        pca_hi = apply_pca_hi(df_bearing, pca_model) if pca_model is not None else None

        held_out = lobo_tree[lobo_tree["bearing_run_id"] == bearing_run_id].sort_values("sequence_index")
        stats = lobo_eval.get(bearing_run_id, {})

        out[bearing_run_id] = {
            "sequence_index": df_bearing["sequence_index"].astype(int).tolist(),
            "reference_hi": [round(float(v), 4) for v in hi],
            "transparent_hi": [round(float(v), 4) for v in transparent_hi] if transparent_hi is not None else None,
            "pca_hi": [round(float(v), 4) for v in pca_hi] if pca_hi is not None else None,
            "stage": stage.tolist(),
            "stage_thresholds": {
                "hi_warn": round(float(thresholds.hi_warn), 4),
                "hi_critical": round(float(thresholds.hi_critical), 4),
                "persistence": int(thresholds.persistence),
            },
            "actual_rul_seconds": [
                round(float(v), 1) if pd.notna(v) else None for v in df_bearing["rul_seconds"]
            ],
            "held_out_predicted_rul_seconds": {
                "sequence_index": held_out["sequence_index"].astype(int).tolist(),
                "predicted_rul_seconds": [round(float(v), 1) for v in held_out["predicted_rul_seconds"]],
            },
            "held_out_metrics": {
                "mae_seconds": stats.get("mae_seconds"),
                "n": stats.get("n"),
                "overestimate_rate": stats.get("overestimate_rate"),
            },
        }

    out_path = REPO_ROOT / "deploy_data" / "trajectory_data.json"
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KiB, {len(out)} bearings)")


if __name__ == "__main__":
    main()
