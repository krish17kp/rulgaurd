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


def score_hidden_set(
    df_censored: pd.DataFrame,
    actual_rul_seconds: dict[str, float],
    predictors: dict[str, "callable"],
) -> pd.DataFrame:
    """Score frozen models against the FEMTO hidden RUL (docs/decisions.md D16).

    This is the project's only genuinely out-of-sample evaluation: the models
    were fit on the 6 learning bearings and have never seen these 11, and the
    targets come from a continuation archive that is never fit on.

    Convention: one prediction per bearing, made at the **last acquisition of the
    censored prefix** - that is the moment the challenge asks "how much life is
    left from here?". Every earlier acquisition is discarded, so this yields 11
    scored points, not 13,959. Small n is inherent to the benchmark; report it.

    `df_censored` must contain only role='test_censored' rows (their
    `rul_seconds` is NaN by construction - the label is external, from
    `actual_rul_seconds`, not from the frame).

    Returns one row per (model, bearing) with the signed error and percent
    error. Positive `error_seconds` means the model predicted MORE remaining
    life than the bearing actually had - the unsafe direction for maintenance
    planning, so it is worth counting separately from raw magnitude.
    """
    roles = set(df_censored["role"].unique())
    if roles != {"test_censored"}:
        raise ValueError(f"score_hidden_set expects only test_censored rows, got roles {roles}")

    rows = []
    for label, actual in sorted(actual_rul_seconds.items()):
        bearing_run_id = f"femto:{label}"
        group = df_censored[df_censored["bearing_run_id"] == bearing_run_id]
        if group.empty:
            continue
        last_acquisition = group.sort_values("sequence_index").iloc[[-1]]

        for model_name, predict in predictors.items():
            predicted = float(predict(last_acquisition).iloc[0])
            error = predicted - actual
            rows.append({
                "model": model_name,
                "bearing": label,
                "condition_id": int(label[len("Bearing")]),
                "n_censored_acquisitions": len(group),
                "actual_rul_seconds": float(actual),
                "predicted_rul_seconds": predicted,
                "error_seconds": error,
                # Challenge convention: positive Er% = UNDER-estimate (predicted
                # less life than actual). Sign is opposite to error_seconds.
                "percent_error": 100.0 * (actual - predicted) / actual,
                "phm2012_score": phm2012_score(100.0 * (actual - predicted) / actual),
            })

    return pd.DataFrame(rows)


def phm2012_score(percent_error: float) -> float:
    """Official IEEE PHM 2012 challenge score for one bearing, from `%Er`.

    Verified against the official challenge document
    (IEEEPHM2012-Challenge-Details.pdf s5.1, eq. 2) and the PRONOSTIA paper
    (Nectoux et al., IEEE PHM 2012, eq. 2), which state it identically:

        A_i = exp(-ln(0.5) * (Er_i /  5))   if Er_i <= 0
        A_i = exp(+ln(0.5) * (Er_i / 20))   if Er_i >  0

    with  %Er_i = 100 * (ActRUL_i - PredRUL_i) / ActRUL_i.

    The asymmetry is the whole point, and its direction is the easiest thing to
    get backwards. `Er > 0` means the model predicted LESS life than the bearing
    had - an *early* warning, penalised leniently (denominator 20). `Er <= 0`
    means it predicted MORE life than the bearing had - a *late* warning, the
    dangerous direction, penalised harshly (denominator 5).

    Sanity points printed on the official figure, both reproduced exactly:
    Er = -10 -> 0.25, Er = +20 -> 0.50. Score is in (0, 1]; higher is better.
    Decay is steep: a 50% over-estimate scores 0.00098.
    """
    if percent_error <= 0:
        return float(np.exp(-np.log(0.5) * (percent_error / 5.0)))
    return float(np.exp(np.log(0.5) * (percent_error / 20.0)))


def summarize_hidden_set(scored: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Per-model aggregates over the hidden set. Reports the over-estimate count
    alongside MAE/RMSE because a model that is wrong in the optimistic direction
    is worse for maintenance than one wrong by the same amount pessimistically."""
    summary = {}
    for model_name, g in scored.groupby("model"):
        err = g["error_seconds"]
        summary[str(model_name)] = {
            "mae_seconds": float(err.abs().mean()),
            "rmse_seconds": float(np.sqrt((err**2).mean())),
            "mean_abs_percent_error": float(g["percent_error"].abs().mean()),
            # Official challenge aggregate: arithmetic mean of A_i over the
            # 11 bearings (challenge doc eq. 3). In (0, 1], higher is better.
            "phm2012_score": float(g["phm2012_score"].mean()),
            "n_bearings": int(len(g)),
            "n_overestimates": int((err > 0).sum()),
        }
    return summary


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
