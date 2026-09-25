#!/usr/bin/env python
"""Run every cross-dataset experiment and persist the results.

Prerequisite: canonical feature Parquets (scripts/build_canonical_features.py).
Datasets whose Parquet is missing are skipped and listed in the output.

Usage:
    python scripts/run_cross_dataset.py --config config/data_paths.toml

Writes (all gitignored):
    reports/metrics/cross_dataset.json                  config, metrics, tables
    reports/metrics/cross_dataset_predictions.parquet   every held-out prediction
    reports/metrics/cross_dataset_applicability.parquet per-bearing applicability
    reports/metrics/cross_dataset_health.parquet        HI + stage per recording
    artifacts/models/cross_domain_bundle.joblib         models used by routing
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import pandas as pd

from bearing_pdm import experiments as E
from bearing_pdm.adapters import ADAPTERS
from bearing_pdm.config import load_data_paths
from bearing_pdm.domain import SN_FEATURES
from bearing_pdm.femto import derive_hidden_rul_seconds
from bearing_pdm.modeling import SEED

CANONICAL = ["canonical_femto_learning", "canonical_femto_test_censored", "canonical_college",
             "canonical_ims", "canonical_xjtu"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/data_paths.toml")
    parser.add_argument("--processed-dir", default="data/processed")
    args = parser.parse_args()
    t0 = time.time()

    processed = Path(args.processed_dir)
    frames, manifests, missing = [], {}, []
    for name in CANONICAL:
        path = processed / f"{name}.parquet"
        if not path.exists():
            missing.append(name)
            continue
        frames.append(pd.read_parquet(path))
        manifests[name] = json.loads(path.with_suffix(".json").read_text())
    print(f"Loaded {[n for n in CANONICAL if n not in missing]}; missing: {missing}")
    df = E.prepare(frames)

    frozen = joblib.load("artifacts/models/rul_extra_trees.joblib")
    reference_hi = joblib.load("artifacts/models/reference_hi_model.joblib")
    paths = load_data_paths(args.config)
    hidden = derive_hidden_rul_seconds(paths.femto_test_dir, paths.femto_validation_dir)

    result = E.run_all(df, frozen, hidden)
    health = E.hi_evaluation(df, reference_hi)
    # Causal degradation stage (FEMTO-fit SN HI) on every prediction row, so
    # errors can also be reported after degradation onset.
    stage_col = E.ROUTING_HI.replace("_hi", "_stage")
    stage = health["health"][["bearing_run_id", "sequence_index", stage_col]]
    pred = result["predictions"].merge(stage.rename(columns={stage_col: "stage"}),
                                       on=["bearing_run_id", "sequence_index"], how="left")
    app = result["applicability"]
    per_bearing = E.bearing_metrics(pred)
    summary = E.summarize(per_bearing)

    out = Path("reports/metrics")
    out.mkdir(parents=True, exist_ok=True)
    pred.to_parquet(out / "cross_dataset_predictions.parquet", index=False)
    app.to_parquet(out / "cross_dataset_applicability.parquet", index=False)
    health["health"].to_parquet(out / "cross_dataset_health.parquet", index=False)

    splits = (pred.groupby(["experiment", "model"])
              .apply(lambda g: {"train_domains": g["train_domains"].iloc[0],
                                "test_bearings": sorted(g["bearing_run_id"].unique())},
                     include_groups=False))
    report = {
        "schema_version": E.RESULTS_SCHEMA_VERSION,
        "config": {
            "seed": SEED, "conformal_alpha": E.ALPHA, "inner_calibration_folds": E.INNER_FOLDS,
            "raw_features": list(frozen.feature_columns), "sn_features": SN_FEATURES,
            "extra_trees": {"n_estimators": frozen.model.n_estimators,
                            "random_state": frozen.model.random_state},
            "reference_windows": {k: list(a.reference_window) for k, a in ADAPTERS.items()},
            "datasets": manifests, "datasets_missing": missing,
            "hidden_rul_seconds_archive_derived": hidden,
            "splits": {f"{e} | {m}": v for (e, m), v in splits.items()},
        },
        "summary": summary.to_dict(orient="records"),
        "per_bearing": per_bearing.to_dict(orient="records"),
        "applicability": app.drop(columns="reasons").to_dict(orient="records"),
        "applicability_vs_error": E.applicability_vs_error(per_bearing, app),
        "health_indicator": health["metrics"],
        "stage_thresholds": {k: vars(v) for k, v in health["stage_thresholds"].items()},
        "routing_hi": E.ROUTING_HI,
        "runtime_s": round(time.time() - t0, 1),
    }
    (out / "cross_dataset.json").write_text(json.dumps(report, indent=2, default=str))

    # Routing may only use a model whose held-out validation showed skill FOR THE
    # KIND OF DATA it is asked about (routing.py). Per dataset: the matching
    # held-out experiment; "unseen": the evidence for a never-seen machine type.
    def skills(experiment_prefix, kind):
        v = per_bearing[per_bearing["experiment"].str.startswith(experiment_prefix)
                        & (per_bearing["model"] == kind)]
        return v.groupby("test_domain")["fraction_skill"].mean().to_dict()

    raw = skills("A: FEMTO -> FEMTO", "raw_seconds") | skills("ZS: FEMTO", "raw_seconds")
    raw["unseen"] = float(pd.Series(skills("ZS: FEMTO", "raw_seconds")).mean())
    multi = skills("MD: all datasets", "sn_fraction")
    multi["unseen"] = float(pd.Series(skills("LODO:", "sn_fraction")).mean())
    for name, table, note in (
            ("raw_seconds", raw, "FEMTO LOBO / zero-shot held-out skill; unseen = mean zero-shot"),
            ("sn_fraction_multi", multi, "multi-dataset LOBO held-out skill; unseen = mean "
                                         "leave-one-domain-out")):
        result["bundle"][name]["skill_by_dataset"] = {k: float(v) for k, v in table.items()}
        result["bundle"][name]["validation_note"] = note
    report["routing_skill_by_dataset"] = {n: result["bundle"][n]["skill_by_dataset"]
                                          for n in ("raw_seconds", "sn_fraction_multi")}
    (out / "cross_dataset.json").write_text(json.dumps(report, indent=2, default=str))
    bundle = result["bundle"] | {"hi_model": health["hi_models"][E.ROUTING_HI],
                                 "stage_thresholds": health["stage_thresholds"][E.ROUTING_HI],
                                 "hi_name": E.ROUTING_HI}
    joblib.dump(bundle, "artifacts/models/cross_domain_bundle.joblib")

    cols = ["experiment", "model", "test_domain", "n_bearings", "mae_seconds", "nmae_life",
            "naive_mae_seconds", "overestimate_pct", "fraction_mae", "fraction_skill",
            "nmae_post_onset", "coverage_conformal", "coverage_conformal_abs", "coverage_tree_5_95"]
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print(summary[cols].round(3).to_string(index=False))
    print(json.dumps(report["applicability_vs_error"], indent=1))
    print(f"Done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
