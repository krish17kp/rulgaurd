"""Leakage-safe RUL evaluation (command.md section 4.3, 12.1).

FEMTO: leave-one-bearing-out over the 6 `role='learning'` bearings (no
random row/window splitting - entire bearings held out).
College: time-ordered expanding-window backtest on the single run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from bearing_pdm.modeling import (
    fit_naive_baseline,
    fit_tree_baseline,
    predict_naive_baseline,
    predict_tree_baseline,
)

ALLOWED_FIT_ROLES = {"learning", "college_run"}


def assert_no_leakage(df: pd.DataFrame, allowed_roles: set[str] = ALLOWED_FIT_ROLES) -> None:
    """Raise before any .fit() call touches df. docs/data-contract.md:
    role='test_censored'/'full_test' rows must never be fit on."""
    bad_roles = set(df["role"].unique()) - allowed_roles
    if bad_roles:
        raise ValueError(
            f"Refusing to fit: rows with role(s) {bad_roles} present - "
            f"only {allowed_roles} may be used for fitting (docs/data-contract.md)."
        )


def _metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    return {"mae_seconds": mae, "rmse_seconds": rmse, "n": len(y_true)}


def leave_one_bearing_out_femto(df_learning: pd.DataFrame) -> pd.DataFrame:
    """Fit naive + tree baselines on 5 bearings, evaluate on the 6th held-out
    bearing, repeated for each of the 6 learning bearings. Returns one row
    per (model, held-out bearing)."""
    assert_no_leakage(df_learning, allowed_roles={"learning"})

    bearings = sorted(df_learning["bearing_run_id"].unique())
    rows = []
    for held_out in bearings:
        train = df_learning[df_learning["bearing_run_id"] != held_out]
        test = df_learning[df_learning["bearing_run_id"] == held_out]

        naive_model = fit_naive_baseline(train)
        naive_pred = predict_naive_baseline(test, naive_model)
        rows.append({"model": "naive", "held_out_bearing": held_out, **_metrics(test["rul_seconds"], naive_pred)})

        tree_model = fit_tree_baseline(train)
        tree_pred = predict_tree_baseline(test, tree_model)
        rows.append({"model": "extra_trees", "held_out_bearing": held_out, **_metrics(test["rul_seconds"], tree_pred)})

    return pd.DataFrame(rows)


def college_walk_forward(df_college: pd.DataFrame, n_folds: int = 4) -> pd.DataFrame:
    """Expanding-window backtest: fold i trains on the first `i` quantile
    slice (chronological, by sequence_index) and tests on the next slice.
    Runtime-asserts every fold is strictly chronological (train max index <
    test min index) - no shuffled/random splitting of the single run."""
    assert_no_leakage(df_college, allowed_roles={"college_run"})

    df_college = df_college.sort_values("sequence_index").reset_index(drop=True)
    n = len(df_college)
    edges = np.linspace(0, n, n_folds + 1, dtype=int)

    rows = []
    for i in range(1, n_folds):
        train = df_college.iloc[: edges[i]]
        test = df_college.iloc[edges[i] : edges[i + 1]]
        if len(test) == 0 or len(train) < 10:
            continue

        assert train["sequence_index"].max() < test["sequence_index"].min(), (
            "Non-chronological college split detected - refusing to evaluate."
        )

        naive_model = fit_naive_baseline(train)
        naive_pred = predict_naive_baseline(test, naive_model)
        rows.append({"model": "naive", "fold": i, **_metrics(test["rul_seconds"], naive_pred)})

        tree_model = fit_tree_baseline(train)
        tree_pred = predict_tree_baseline(test, tree_model)
        rows.append({"model": "extra_trees", "fold": i, **_metrics(test["rul_seconds"], tree_pred)})

    return pd.DataFrame(rows)
