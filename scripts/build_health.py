#!/usr/bin/env python
"""Fit + evaluate both health indicators on FEMTO learning-set features.

Usage:
    python scripts/build_health.py --config config/data_paths.toml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from bearing_pdm.config import load_data_paths
from bearing_pdm.health import (
    apply_pca_hi,
    apply_transparent_hi,
    evaluate_hi,
    fit_pca_hi,
    fit_transparent_hi_baseline,
)
from bearing_pdm.storage import get_connection


def _latest_femto_learning_parquet(con) -> Path:
    row = con.execute(
        "SELECT parquet_path FROM feature_batches WHERE dataset_id = 'femto' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("No femto feature_batches found - run build_features.py --dataset femto first.")
    return Path(row[0])


def _plot_hi(df: pd.DataFrame, hi: pd.Series, title: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    tmp = df.assign(hi=hi.to_numpy())
    for bearing, g in tmp.sort_values("sequence_index").groupby("bearing_run_id"):
        ax.plot(g["sequence_index"], g["hi"], label=bearing, linewidth=1)
    ax.set_xlabel("acquisition index (life progression)")
    ax.set_ylabel("health indicator (1=healthy, 0=failed)")
    ax.set_title(title)
    ax.legend(fontsize=7)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


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
    print(f"Loaded {len(df)} learning-role rows from {parquet_path}")

    baseline = fit_transparent_hi_baseline(df)
    hi_transparent = apply_transparent_hi(df, baseline)
    report_transparent = evaluate_hi(df, hi_transparent)

    pca_model = fit_pca_hi(df, top_k=8)
    hi_pca = apply_pca_hi(df, pca_model)
    report_pca = evaluate_hi(df, hi_pca)

    print("\n=== Transparent HI ===")
    print(report_transparent.to_string(index=False))
    print("\n=== Paper-inspired PCA HI ===")
    print(f"selected features: {pca_model.selected_features}")
    print(report_pca.to_string(index=False))

    metrics = {
        "transparent_hi": {
            "mean_monotonicity": float(report_transparent["monotonicity"].mean()),
            "mean_trend_corr": float(report_transparent["trend_corr"].mean()),
            "per_bearing": report_transparent.to_dict(orient="records"),
        },
        "pca_hi": {
            "selected_features": list(pca_model.selected_features),
            "mean_monotonicity": float(report_pca["monotonicity"].mean()),
            "mean_trend_corr": float(report_pca["trend_corr"].mean()),
            "per_bearing": report_pca.to_dict(orient="records"),
        },
    }
    selected = "pca_hi" if abs(metrics["pca_hi"]["mean_trend_corr"]) > abs(
        metrics["transparent_hi"]["mean_trend_corr"]
    ) else "transparent_hi"
    metrics["selected"] = selected
    metrics["selection_reason"] = "higher |mean trend correlation| across the 6 learning bearings"

    metrics_path = Path("reports/metrics/health_indicator_comparison.json")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2))
    print(f"\nWrote {metrics_path}")

    _plot_hi(df, hi_transparent, "Transparent HI (z-score of RMS+kurtosis)", Path("reports/figures/hi_transparent.png"))
    _plot_hi(df, hi_pca, "Paper-inspired PCA HI", Path("reports/figures/hi_pca.png"))
    print("Wrote reports/figures/hi_transparent.png, reports/figures/hi_pca.png")

    models_dir = Path("artifacts/models")
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(baseline, models_dir / "transparent_hi_baseline.joblib")
    joblib.dump(pca_model, models_dir / "pca_hi_model.joblib")
    print(f"Wrote {models_dir}/transparent_hi_baseline.joblib, {models_dir}/pca_hi_model.joblib")

    print(f"\nSelected: {selected} ({metrics['selection_reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
