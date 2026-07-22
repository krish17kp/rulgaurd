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
from bearing_pdm.evaluation import college_walk_forward, leave_one_bearing_out_femto
from bearing_pdm.storage import get_connection


def _latest_batch_parquet(con, dataset_id: str) -> Path | None:
    row = con.execute(
        "SELECT parquet_path FROM feature_batches WHERE dataset_id = ? ORDER BY created_at DESC LIMIT 1",
        [dataset_id],
    ).fetchone()
    return Path(row[0]) if row else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    paths = load_data_paths(args.config)
    con = get_connection(paths.duckdb_path)
    try:
        femto_path = _latest_batch_parquet(con, "femto")
        college_path = _latest_batch_parquet(con, "college")
    finally:
        con.close()

    results = {}

    if femto_path is not None:
        df_femto = pd.read_parquet(femto_path)
        df_femto = df_femto[df_femto["role"] == "learning"].reset_index(drop=True)
        print(f"FEMTO: {len(df_femto)} learning rows from {femto_path}")
        femto_results = leave_one_bearing_out_femto(df_femto)
        print("\n=== FEMTO leave-one-bearing-out ===")
        print(femto_results.to_string(index=False))
        results["femto_lobo"] = femto_results.to_dict(orient="records")
        results["femto_lobo_mean_mae_by_model"] = (
            femto_results.groupby("model")["mae_seconds"].mean().to_dict()
        )

    if college_path is not None:
        df_college = pd.read_parquet(college_path)
        print(f"\ncollege: {len(df_college)} rows from {college_path}")
        college_results = college_walk_forward(df_college)
        print("\n=== college walk-forward ===")
        print(college_results.to_string(index=False))
        results["college_walk_forward"] = college_results.to_dict(orient="records")
        results["college_mean_mae_by_model"] = (
            college_results.groupby("model")["mae_seconds"].mean().to_dict()
        )

    out_path = Path("reports/metrics/rul_evaluation.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
