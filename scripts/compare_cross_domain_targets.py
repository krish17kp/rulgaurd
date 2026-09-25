#!/usr/bin/env python
"""Evidence for docs/decisions.md D24: which target should the cross-domain
(self-normalised-feature) ExtraTrees regress on?

Compares, on identical held-out rows, a life-fraction target f against the
log-ratio target y = log((1 - f) / f) (its negated logit), both judged by the
life-fraction MAE and against a label-free constant guess f = 0.5. Splits:
FEMTO leave-one-bearing-out and FEMTO -> college zero-shot.

Writes reports/metrics/cross_domain_target_comparison.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from bearing_pdm import experiments as E
from bearing_pdm.domain import SN_FEATURES
from bearing_pdm.modeling import bearing_balanced_weights, fit_tree_baseline


def main() -> int:
    frames = [pd.read_parquet(f"data/processed/canonical_{n}.parquet")
              for n in ("femto_learning", "college")]
    df = E.run_to_failure(E.prepare(frames))
    f = np.clip(df["life_fraction"], 0.005, 0.995)
    df["log_ratio"] = np.log((1 - f) / f)
    femto = df[df["dataset_id"] == "femto"]
    splits = [(b, femto[femto["bearing_run_id"] != b], femto[femto["bearing_run_id"] == b])
              for b in sorted(femto["bearing_run_id"].unique())]
    splits.append(("college (zero-shot)", femto, df[df["dataset_id"] == "college"]))

    rows = []
    for name, train, test in splits:
        test = test[test["evaluable"]]
        truth = test["life_fraction"].to_numpy()
        preds = {}
        for target in ("life_fraction", "log_ratio"):
            m = fit_tree_baseline(train, feature_columns=SN_FEATURES, target=target,
                                  sample_weight=bearing_balanced_weights(train))
            p = m.model.predict(test[SN_FEATURES].fillna(m.median_fill))
            preds[target] = p if target == "life_fraction" else 1 / (1 + np.exp(p))
        rows.append({"test": name,
                     "fraction_mae_f_target": float(np.abs(preds["life_fraction"] - truth).mean()),
                     "fraction_mae_logratio_target": float(np.abs(preds["log_ratio"] - truth).mean()),
                     "fraction_mae_constant_0.5": float(np.abs(0.5 - truth).mean()),
                     "spearman_pred_vs_truth_f_target": float(
                         pd.Series(preds["life_fraction"]).corr(pd.Series(truth), method="spearman"))})
    out = Path("reports/metrics/cross_domain_target_comparison.json")
    out.write_text(json.dumps(rows, indent=2))
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
