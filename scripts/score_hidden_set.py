#!/usr/bin/env python
"""Score the frozen RUL pipeline against FEMTO's hidden RUL (docs/decisions.md D16).

This is the project's only genuinely out-of-sample evaluation. The models in
artifacts/models/ were fit on the 6 learning bearings only; the 11 test bearings
here have never been seen, and their targets come from the Full_Test_Set
continuation archive, which is never fit on anything.

Ground truth is re-derived from the archives on disk
(femto.derive_hidden_rul_seconds) and cross-checked against the published table
(femto.PUBLISHED_HIDDEN_RUL_S). A mismatch aborts the run rather than scoring
against numbers that do not describe the local data.

Prerequisites:
    python scripts/build_features.py --dataset femto --config config/data_paths.toml --role test_censored
    python scripts/train_models.py --config config/data_paths.toml

Usage:
    python scripts/score_hidden_set.py --config config/data_paths.toml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

from bearing_pdm.config import load_data_paths
from bearing_pdm.evaluation import score_hidden_set, summarize_hidden_set
from bearing_pdm.femto import (
    BEARING1_4_DERIVED_RUL_S,
    OFFICIAL_HIDDEN_RUL_S,
    derive_hidden_rul_seconds,
)
from bearing_pdm.modeling import predict_naive_baseline, predict_tree_baseline
from bearing_pdm.storage import get_connection, latest_batch_parquet

METRICS_PATH = Path("reports/metrics/hidden_set_evaluation.json")


def _resolve_ground_truth(paths) -> tuple[dict[str, float], dict[str, float]]:
    """Return (official, derived) hidden-RUL tables, cross-checked.

    Bearing1_4 is a known, documented disagreement (docs/decisions.md D17):
    official 339 s vs 2890 s derived from the archives. Any OTHER mismatch means
    the local archives are not the official ones, and scoring against them would
    be meaningless - so that aborts.
    """
    derived = derive_hidden_rul_seconds(paths.femto_test_dir, paths.femto_validation_dir)
    if not derived:
        raise RuntimeError(
            f"No test bearings found under {paths.femto_test_dir} / "
            f"{paths.femto_validation_dir}. Extract the FEMTO archives first."
        )

    unexpected = {
        b: (derived.get(b), official)
        for b, official in OFFICIAL_HIDDEN_RUL_S.items()
        if derived.get(b) != official and b != "Bearing1_4"
    }
    if unexpected:
        raise RuntimeError(
            "Derived hidden RUL disagrees with the official table on bearings "
            f"other than the known Bearing1_4 case - refusing to score: {unexpected}"
        )

    if derived.get("Bearing1_4") != BEARING1_4_DERIVED_RUL_S:
        raise RuntimeError(
            f"Bearing1_4 derived {derived.get('Bearing1_4')}s, expected the "
            f"documented {BEARING1_4_DERIVED_RUL_S}s (docs/decisions.md D17)."
        )

    print(
        f"Ground truth: {len(derived)} bearings re-derived from the archives; "
        f"{len(OFFICIAL_HIDDEN_RUL_S) - 1}/{len(OFFICIAL_HIDDEN_RUL_S)} match the "
        "official table exactly.\n"
        f"  Bearing1_4 is the documented exception: official {OFFICIAL_HIDDEN_RUL_S['Bearing1_4']}s "
        f"vs {BEARING1_4_DERIVED_RUL_S}s derived (D17). Both are reported below."
    )
    return dict(OFFICIAL_HIDDEN_RUL_S), derived


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    paths = load_data_paths(args.config)
    official_rul, derived_rul = _resolve_ground_truth(paths)

    con = get_connection(paths.duckdb_path)
    try:
        censored_path = latest_batch_parquet(con, "femto", role="test_censored")
    finally:
        con.close()
    if censored_path is None:
        raise RuntimeError(
            "No femto batch with test_censored rows. Run: build_features.py "
            "--dataset femto --role test_censored"
        )

    df = pd.read_parquet(censored_path)
    df = df[df["role"] == "test_censored"].reset_index(drop=True)
    print(f"Loaded {len(df)} censored acquisitions from {censored_path}")

    models_dir = Path("artifacts/models")
    tree = joblib.load(models_dir / "rul_extra_trees.joblib")
    naive = joblib.load(models_dir / "rul_naive.joblib")
    predictors = {
        "extra_trees": lambda frame: predict_tree_baseline(frame, tree),
        "naive": lambda frame: predict_naive_baseline(frame, naive),
    }

    variants = {}
    for variant, actual_rul in (("official", official_rul), ("archive_derived", derived_rul)):
        scored = score_hidden_set(df, actual_rul, predictors)
        summary = summarize_hidden_set(scored)
        variants[variant] = {"per_bearing": scored, "summary": summary}

        print(
            f"\n=== FEMTO hidden set, ground truth = {variant} "
            "(prediction at last censored acquisition) ==="
        )
        for model_name in sorted(summary):
            g = scored[scored["model"] == model_name].sort_values("bearing")
            print(f"\n-- {model_name} --")
            print(
                g[["bearing", "condition_id", "actual_rul_seconds",
                   "predicted_rul_seconds", "error_seconds", "percent_error",
                   "phm2012_score"]]
                .to_string(index=False, float_format=lambda v: f"{v:.3f}")
            )
            s = summary[model_name]
            print(
                f"   MAE={s['mae_seconds']:.1f}s  RMSE={s['rmse_seconds']:.1f}s  "
                f"mean|Er%|={s['mean_abs_percent_error']:.1f}%  "
                f"PHM2012 score={s['phm2012_score']:.4f}  "
                f"over-estimates={s['n_overestimates']}/{s['n_bearings']}"
            )

    official_summary = variants["official"]["summary"]
    best = min(official_summary, key=lambda m: official_summary[m]["mae_seconds"])
    print(f"\nLower MAE on the hidden set (official ground truth): {best}")

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps({
        "convention": (
            "One prediction per bearing at the last acquisition of the censored "
            "prefix. n=11 bearings, not 13959 acquisitions."
        ),
        "scoring_function": (
            "PHM2012 A_i = exp(-ln(0.5)*Er/5) for Er<=0 (over-estimate, harsh); "
            "exp(+ln(0.5)*Er/20) for Er>0 (under-estimate, lenient); "
            "Er = 100*(actual-predicted)/actual. Verified against "
            "IEEEPHM2012-Challenge-Details.pdf s5.1 eq.2 and Nectoux et al. "
            "(PRONOSTIA, IEEE PHM 2012) eq.2. Aggregate = arithmetic mean (eq.3)."
        ),
        "ground_truth_variants": {
            "official": (
                "Table 3 of the official challenge document - the citable, "
                "literature-comparable table."
            ),
            "archive_derived": (
                "(Full_Test_Set acc count - Test_set acc count) * 10s, re-derived "
                "from the archives. Agrees with official on 10/11 bearings; "
                "Bearing1_4 differs (339s official vs 2890s derived) - see D17."
            ),
        },
        "official_rul_seconds": official_rul,
        "archive_derived_rul_seconds": derived_rul,
        "results": {
            v: {
                "per_bearing": d["per_bearing"].to_dict(orient="records"),
                "summary_by_model": d["summary"],
            }
            for v, d in variants.items()
        },
        "lower_mae_model_official": best,
    }, indent=2))
    print(f"Wrote {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
