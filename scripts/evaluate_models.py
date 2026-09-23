#!/usr/bin/env python
"""Leakage-safe RUL evaluation: leave-one-bearing-out on FEMTO learning
bearings, time-ordered expanding-window walk-forward on the college run.

Usage:
    python scripts/evaluate_models.py --config config/data_paths.toml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from bearing_pdm.config import load_data_paths
from bearing_pdm.evaluation import (
    college_walk_forward,
    leave_one_bearing_out_femto,
    summarize_predictions,
)
from bearing_pdm.storage import get_connection, latest_batch_parquet


def _latest_batch_parquet(con, dataset_id: str, role: str | None = None) -> Path | None:
    return latest_batch_parquet(con, dataset_id, role=role)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    paths = load_data_paths(args.config)
    con = get_connection(paths.duckdb_path)
    try:
        # role= is required: once a test_censored batch exists it is the newest
        # femto batch, and this evaluation is defined over learning rows (D15).
        femto_path = _latest_batch_parquet(con, "femto", role="learning")
        college_path = _latest_batch_parquet(con, "college", role="college_run")
    finally:
        con.close()

    results = {}
    prediction_frames = []

    if femto_path is not None:
        df_femto = pd.read_parquet(femto_path)
        df_femto = df_femto[df_femto["role"] == "learning"].reset_index(drop=True)
        print(f"FEMTO: {len(df_femto)} learning rows from {femto_path}")
        femto_results, femto_predictions = leave_one_bearing_out_femto(df_femto)
        print("\n=== FEMTO leave-one-bearing-out ===")
        print(femto_results.to_string(index=False))
        results["femto_lobo"] = femto_results.to_dict(orient="records")
        results["femto_lobo_mean_mae_by_model"] = (
            femto_results.groupby("model")["mae_seconds"].mean().to_dict()
        )
        results["femto_lobo_overall_by_model"] = summarize_predictions(femto_predictions)
        prediction_frames.append(femto_predictions.assign(dataset_id="femto"))

    if college_path is not None:
        df_college = pd.read_parquet(college_path)
        print(f"\ncollege: {len(df_college)} rows from {college_path}")
        college_results, college_predictions = college_walk_forward(df_college)
        print("\n=== college walk-forward ===")
        print(college_results.to_string(index=False))
        results["college_walk_forward"] = college_results.to_dict(orient="records")
        results["college_mean_mae_by_model"] = (
            college_results.groupby("model")["mae_seconds"].mean().to_dict()
        )
        results["college_overall_by_model"] = summarize_predictions(college_predictions)
        # D10 travels with the artifact: anything that reads this file gets the
        # reason the college naive MAE is 0.0 in the same breath as the number,
        # so it cannot be quoted as a result on its own.
        results["college_naive_caveat"] = (
            "College rul_seconds = run_end_timestamp - event_timestamp, and the naive baseline "
            "predicts mean_total_life - elapsed. On an expanding window that always starts at "
            "the true t=0 those are algebraically the same formula, so naive scores MAE=0.0 by "
            "construction (docs/decisions.md D10). It is an oracle with access to the true total "
            "run length, not a fair comparison for ExtraTrees."
        )
        prediction_frames.append(college_predictions.assign(dataset_id="college"))

    out_path = Path("reports/metrics/rul_evaluation.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {out_path}")

    if prediction_frames:
        predictions_path = out_path.parent / "rul_predictions.parquet"
        pd.concat(prediction_frames, ignore_index=True).to_parquet(predictions_path, index=False)
        print(f"Wrote {predictions_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
