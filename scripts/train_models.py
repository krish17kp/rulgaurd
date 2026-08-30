#!/usr/bin/env python
"""Fit and freeze the final RUL pipeline on all FEMTO learning-role data
(evaluate_models.py already established leakage-safe out-of-sample
performance via leave-one-bearing-out - this script fits the frozen model
used for real predictions on ALL 6 learning bearings, then saves it).

Usage:
    python scripts/train_models.py --config config/data_paths.toml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

from bearing_pdm.config import load_data_paths
from bearing_pdm.modeling import fit_naive_baseline, fit_tree_baseline
from bearing_pdm.storage import get_connection, latest_batch_parquet


def _latest_femto_learning_parquet(con) -> Path:
    path = latest_batch_parquet(con, "femto", role="learning")
    if path is None:
        raise RuntimeError(
            "No femto feature batch containing learning-role rows found - "
            "run build_features.py --dataset femto --role learning first."
        )
    return path


def _select_model(eval_metrics_path: Path) -> str:
    """Pick the model with lower mean LOBO MAE, per evaluate_models.py's
    output. Defaults to extra_trees if no evaluation has been run yet."""
    if not eval_metrics_path.exists():
        return "extra_trees"
    metrics = json.loads(eval_metrics_path.read_text())
    by_model = metrics.get("femto_lobo_mean_mae_by_model")
    if not by_model:
        return "extra_trees"
    return min(by_model, key=by_model.get)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    paths = load_data_paths(args.config)
    con = get_connection(paths.duckdb_path)
    try:
        parquet_path = _latest_femto_learning_parquet(con)
    finally:
        con.close()

    df = pd.read_parquet(parquet_path)
    df = df[df["role"] == "learning"].reset_index(drop=True)
    print(f"Fitting on {len(df)} learning-role rows from {parquet_path} (all 6 bearings, frozen)")

    naive_model = fit_naive_baseline(df)
    tree_model = fit_tree_baseline(df)

    models_dir = Path("artifacts/models")
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(naive_model, models_dir / "rul_naive.joblib")
    joblib.dump(tree_model, models_dir / "rul_extra_trees.joblib")
    print(f"Wrote {models_dir}/rul_naive.joblib, {models_dir}/rul_extra_trees.joblib")

    selected = _select_model(Path("reports/metrics/rul_evaluation.json"))
    (models_dir / "rul_selected_model.json").write_text(json.dumps({
        "selected": selected,
        "reason": "lower mean leave-one-bearing-out MAE (reports/metrics/rul_evaluation.json)",
    }, indent=2))
    print(f"Selected pipeline: {selected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
