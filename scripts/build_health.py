#!/usr/bin/env python
"""Fit + compare all three health indicators on FEMTO learning-set features,
then fit M5 degradation-stage thresholds on the selected one.

Three HIs are reported side by side on purpose (docs/decisions.md D18). The
first two are kept because their measured failure modes are the evidence for
why the third exists, not because they are still candidates:

  transparent_hi  hard floor + pooled healthy reference -> pins ~47.5% of all
                  learning acquisitions at exactly 1.0
  pca_hi          outlier-driven pooled min-max -> usable range collapses
  reference_hi    per-bearing healthy reference, robust train-frozen scale,
                  logistic map -> pinning is structurally impossible

Also runs a leave-one-bearing-out calibration pass for the reference HI and the
stage thresholds. LOBO is the honest number: nothing the held-out bearing
contains reaches the values it is judged against.

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
import numpy as np
import pandas as pd

from bearing_pdm.config import load_data_paths
from bearing_pdm.health import (
    REFERENCE_HI_N,
    REFERENCE_HI_SKIP,
    apply_pca_hi,
    apply_reference_hi,
    apply_transparent_hi,
    evaluate_hi,
    fit_pca_hi,
    fit_reference_hi,
    fit_transparent_hi_baseline,
    reference_hi_diagnostics,
)
from bearing_pdm.stages import (
    STAGE_ORDER,
    assign_stages,
    fit_stage_thresholds,
    summarize_stages,
)
from bearing_pdm.storage import get_connection, latest_batch_parquet

SMOOTHING_SWEEP = (1, 5, 11, 21, 31)


def _latest_femto_learning_parquet(con) -> Path:
    path = latest_batch_parquet(con, "femto", role="learning")
    if path is None:
        raise RuntimeError(
            "No femto feature batch containing learning-role rows found - "
            "run build_features.py --dataset femto --role learning first."
        )
    return path


def _plot_hi(df: pd.DataFrame, hi: pd.Series, title: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    tmp = df.assign(hi=hi.to_numpy())
    for bearing, g in tmp.sort_values("sequence_index").groupby("bearing_run_id"):
        ax.plot(g["sequence_index"], g["hi"], label=bearing, linewidth=1)
    ax.set_xlabel("acquisition index (life progression)")
    ax.set_ylabel("health indicator (1=healthy, 0=failed)")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title(title)
    ax.legend(fontsize=7)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _pinning_report(hi: pd.Series, df: pd.DataFrame) -> dict[str, float]:
    """The blocker, quantified the same way for every HI so the three are
    directly comparable."""
    per_bearing = []
    for _bearing, g in df.assign(_hi=hi.to_numpy()).groupby("bearing_run_id"):
        values = g["_hi"].to_numpy()
        per_bearing.append({
            "pct_at_one": float(100.0 * np.mean(values >= 0.999)),
            "usable_range_p05_p95": float(
                np.nanpercentile(values, 95) - np.nanpercentile(values, 5)
            ),
        })
    return {
        "mean_pct_at_one": float(np.mean([r["pct_at_one"] for r in per_bearing])),
        "worst_pct_at_one": float(np.max([r["pct_at_one"] for r in per_bearing])),
        "mean_usable_range_p05_p95": float(
            np.mean([r["usable_range_p05_p95"] for r in per_bearing])
        ),
    }


def _lobo_reference_hi(df: pd.DataFrame) -> pd.Series:
    """Fit on 5 bearings, apply to the 6th, for each of the 6."""
    parts = []
    for bearing in sorted(df["bearing_run_id"].unique()):
        train = df[df["bearing_run_id"] != bearing]
        test = df[df["bearing_run_id"] == bearing]
        parts.append(apply_reference_hi(test, fit_reference_hi(train)))
    return pd.concat(parts).sort_index()


def _smoothing_sweep(df: pd.DataFrame) -> list[dict[str, float]]:
    """Evidence for the chosen smoothing width. A window that is too wide
    cannot resolve a terminal cliff - FEMTO's Bearing3_1 degrades inside its
    final ~17 acquisitions."""
    rows = []
    for window in SMOOTHING_SWEEP:
        model = fit_reference_hi(df, smooth_window=window)
        report = reference_hi_diagnostics(df, apply_reference_hi(df, model))
        rows.append({
            "smooth_window": int(window),
            "mean_spearman": float(report["spearman"].mean()),
            "worst_pct_at_one": float(report["pct_at_one"].max()),
            "mean_hi_final_1pct": float(report["hi_final_1pct"].mean()),
            "worst_hi_final_1pct": float(report["hi_final_1pct"].max()),
        })
    return rows


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
    df = df[df["role"] == "learning"].sort_values(
        ["bearing_run_id", "sequence_index"]
    ).reset_index(drop=True)
    print(f"Loaded {len(df)} learning-role rows from {parquet_path}")

    baseline = fit_transparent_hi_baseline(df)
    hi_transparent = apply_transparent_hi(df, baseline)
    report_transparent = evaluate_hi(df, hi_transparent)

    pca_model = fit_pca_hi(df, top_k=8)
    hi_pca = apply_pca_hi(df, pca_model)
    report_pca = evaluate_hi(df, hi_pca)

    reference_model = fit_reference_hi(df)
    hi_reference = apply_reference_hi(df, reference_model)
    hi_reference_lobo = _lobo_reference_hi(df)
    report_reference = reference_hi_diagnostics(df, hi_reference)
    report_reference_lobo = reference_hi_diagnostics(df, hi_reference_lobo)

    print("\n=== Transparent HI (legacy - pins at 1.0, see D18) ===")
    print(report_transparent.to_string(index=False))
    print("\n=== Paper-inspired PCA HI (legacy - collapsed range, see D18) ===")
    print(f"selected features: {pca_model.selected_features}")
    print(report_pca.to_string(index=False))
    print("\n=== Reference HI, pooled calibration ===")
    print(report_reference.to_string(index=False))
    print("\n=== Reference HI, leave-one-bearing-out calibration (the honest number) ===")
    print(report_reference_lobo.to_string(index=False))

    # --- selection -------------------------------------------------------
    # An HI that pins is not a candidate whatever its trend correlation:
    # a constant cannot carry a degradation stage. Among HIs that clear the
    # pinning gate, prefer the strongest rank trend against life progression.
    # Spearman rather than Pearson because FEMTO degradation is flat-then-cliff.
    candidates = {
        "transparent_hi": (_pinning_report(hi_transparent, df), report_transparent["spearman"]),
        "pca_hi": (_pinning_report(hi_pca, df), report_pca["spearman"]),
        "reference_hi": (_pinning_report(hi_reference_lobo, df), report_reference_lobo["spearman"]),
    }
    PIN_GATE = 5.0  # percent of a bearing's acquisitions allowed at exactly 1.0
    eligible = {
        name: abs(float(trend.mean()))
        for name, (pinning, trend) in candidates.items()
        if pinning["worst_pct_at_one"] < PIN_GATE
    }
    if not eligible:
        raise RuntimeError(
            "No health indicator cleared the pinning gate - refusing to select one. "
            "A stage classifier built on a pinned HI would be meaningless."
        )
    selected = max(eligible, key=eligible.__getitem__)

    # --- M5 stages on the selected HI ------------------------------------
    stage_thresholds = fit_stage_thresholds(df, hi_reference, REFERENCE_HI_SKIP, REFERENCE_HI_N)
    stage_summary_rows = []
    for bearing in sorted(df["bearing_run_id"].unique()):
        train = df[df["bearing_run_id"] != bearing]
        test = df[df["bearing_run_id"] == bearing]
        fold_model = fit_reference_hi(train)
        fold_thresholds = fit_stage_thresholds(
            train, apply_reference_hi(train, fold_model), REFERENCE_HI_SKIP, REFERENCE_HI_N
        )
        fold_stages = assign_stages(test, apply_reference_hi(test, fold_model), fold_thresholds)
        row = summarize_stages(test, fold_stages)
        row["hi_warn"] = fold_thresholds.hi_warn
        row["hi_critical"] = fold_thresholds.hi_critical
        stage_summary_rows.append(row)
    stage_summary = pd.concat(stage_summary_rows, ignore_index=True)

    print("\n=== M5 degradation stages, leave-one-bearing-out ===")
    print(f"stages: {' < '.join(STAGE_ORDER)} (severity bands on the HI, NOT fault types)")
    print(stage_summary.to_string(index=False))

    metrics = {
        "transparent_hi": {
            "status": "legacy - retained as documented failure (docs/decisions.md D18)",
            "failure_mode": "hard floor at anomaly=0 plus a healthy reference pooled across "
                            "three operating conditions pins most acquisitions at exactly 1.0",
            "mean_monotonicity": float(report_transparent["monotonicity"].mean()),
            "mean_trend_corr": float(report_transparent["trend_corr"].mean()),
            "mean_spearman": float(report_transparent["spearman"].mean()),
            "pinning": _pinning_report(hi_transparent, df),
            "per_bearing": report_transparent.to_dict(orient="records"),
        },
        "pca_hi": {
            "status": "legacy - retained as documented failure (docs/decisions.md D18)",
            "failure_mode": "pooled PC1 min-max is set by rare end-of-life spikes, so the "
                            "usable range collapses",
            "selected_features": list(pca_model.selected_features),
            "mean_monotonicity": float(report_pca["monotonicity"].mean()),
            "mean_trend_corr": float(report_pca["trend_corr"].mean()),
            "mean_spearman": float(report_pca["spearman"].mean()),
            "pinning": _pinning_report(hi_pca, df),
            "per_bearing": report_pca.to_dict(orient="records"),
        },
        "reference_hi": {
            "status": "current",
            "features": list(reference_model.features),
            "log_features": list(reference_model.log_features),
            "reference_window_acquisitions": [
                reference_model.reference_skip,
                reference_model.reference_skip + reference_model.reference_n,
            ],
            "smooth_window": reference_model.smooth_window,
            "healthy_score": reference_model.healthy_score,
            "failure_score": reference_model.failure_score,
            "pooled": {
                "mean_spearman": float(report_reference["spearman"].mean()),
                "pinning": _pinning_report(hi_reference, df),
                "per_bearing": report_reference.to_dict(orient="records"),
            },
            "leave_one_bearing_out": {
                "mean_spearman": float(report_reference_lobo["spearman"].mean()),
                "pinning": _pinning_report(hi_reference_lobo, df),
                "per_bearing": report_reference_lobo.to_dict(orient="records"),
            },
            "smoothing_window_sweep": _smoothing_sweep(df),
        },
        "selection": {
            "selected": selected,
            "gate": f"worst per-bearing pct_at_one < {PIN_GATE}% (a pinned HI cannot carry a "
                    "degradation stage), then strongest |mean rank trend| vs life progression",
            "eligible": eligible,
            "ineligible": {
                name: pinning["worst_pct_at_one"]
                for name, (pinning, _) in candidates.items()
                if name not in eligible
            },
        },
        "stages": {
            "method": "statistical alarm band on the selected HI plus a persistence rule. "
                      "hi_warn is a genuine fitted quantile of the training bearings' healthy "
                      "HI. hi_critical is a quantile of HI values already compressed by the "
                      "reference HI's fixed /6 logistic steepness toward a constant end-of-life "
                      "anchor (~0.047, docs/decisions.md D20) - a threshold computed from data, "
                      "but not an independent fit the way hi_warn is",
            "order": list(STAGE_ORDER),
            "not_a_diagnosis": "a stage is a severity band on a health indicator, not a fault "
                               "type - no inner-race/outer-race/ball/cage/lubrication claim",
            "persistence_acquisitions": stage_thresholds.persistence,
            "pooled_thresholds": {
                "hi_warn": stage_thresholds.hi_warn,
                "hi_critical": stage_thresholds.hi_critical,
            },
            "leave_one_bearing_out": stage_summary.to_dict(orient="records"),
        },
    }
    # Kept for backward compatibility with anything reading the old shape.
    metrics["selected"] = selected
    metrics["selection_reason"] = metrics["selection"]["gate"]

    metrics_path = Path("reports/metrics/health_indicator_comparison.json")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2))
    print(f"\nWrote {metrics_path}")

    _plot_hi(df, hi_transparent, "Transparent HI (legacy - pins at 1.0)",
             Path("reports/figures/hi_transparent.png"))
    _plot_hi(df, hi_pca, "Paper-inspired PCA HI (legacy - collapsed range)",
             Path("reports/figures/hi_pca.png"))
    _plot_hi(df, hi_reference_lobo, "Reference HI (leave-one-bearing-out calibration)",
             Path("reports/figures/hi_reference.png"))
    print("Wrote reports/figures/hi_transparent.png, hi_pca.png, hi_reference.png")

    models_dir = Path("artifacts/models")
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(baseline, models_dir / "transparent_hi_baseline.joblib")
    joblib.dump(pca_model, models_dir / "pca_hi_model.joblib")
    joblib.dump(reference_model, models_dir / "reference_hi_model.joblib")
    joblib.dump(stage_thresholds, models_dir / "stage_thresholds.joblib")
    print(f"Wrote {models_dir}/{{transparent_hi_baseline,pca_hi_model,"
          f"reference_hi_model,stage_thresholds}}.joblib")

    print(f"\nSelected: {selected}")
    print(f"  eligible (cleared the pinning gate): {eligible}")
    print(f"  ineligible (worst pct_at_one): {metrics['selection']['ineligible']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
