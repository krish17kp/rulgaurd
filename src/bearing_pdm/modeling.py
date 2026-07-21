"""RUL regression baselines (command.md section 12.1).

Required: naive baseline, one tree-based baseline (ExtraTreesRegressor).
Small, documented hyperparameters - no broad search (command.md section
26.7: "the first review objective is a valid baseline, not the best
possible score").
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor

from bearing_pdm.health import candidate_feature_columns

SEED = 42  # config/project.example.toml [seed]
TARGET_COLUMN = "rul_seconds"


def _elapsed_seconds(df: pd.DataFrame, bearing_start_times: dict[str, "pd.Timestamp"]) -> pd.Series:
    """Seconds since each bearing_run_id's TRUE absolute start, using a
    fixed start-time mapping (not recomputed from whatever slice is passed
    in - see docs/decisions.md D9: recomputing per-slice broke the college
    walk-forward evaluation, where later folds' test slices start mid-run,
    not at t=0). Falls back to the row's own group-min for a bearing_run_id
    not seen in the mapping (best available estimate for a truly unseen
    bearing at predict time)."""
    known_start = df["bearing_run_id"].map(bearing_start_times)
    fallback_start = df.groupby("bearing_run_id")["event_timestamp"].transform("min")
    start = known_start.fillna(fallback_start)
    return (df["event_timestamp"] - start).dt.total_seconds()


# ---------------------------------------------------------------------------
# Naive baseline: predict the training-mean total bearing life, minus
# elapsed time so far. No model fitting beyond one scalar mean + per-bearing
# start-time lookup.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NaiveBaseline:
    mean_total_life_seconds: float
    bearing_start_times: dict[str, "pd.Timestamp"]


def fit_naive_baseline(df_train: pd.DataFrame) -> NaiveBaseline:
    total_life_per_bearing = df_train.groupby("bearing_run_id")[TARGET_COLUMN].max()
    start_times = df_train.groupby("bearing_run_id")["event_timestamp"].min().to_dict()
    return NaiveBaseline(
        mean_total_life_seconds=float(total_life_per_bearing.mean()), bearing_start_times=start_times
    )


def predict_naive_baseline(df: pd.DataFrame, model: NaiveBaseline) -> pd.Series:
    elapsed = _elapsed_seconds(df, model.bearing_start_times)
    return (model.mean_total_life_seconds - elapsed).clip(lower=0)


# ---------------------------------------------------------------------------
# Tree-based baseline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TreeBaseline:
    feature_columns: tuple[str, ...]
    model: ExtraTreesRegressor
    median_fill: dict[str, float]


def fit_tree_baseline(
    df_train: pd.DataFrame, n_estimators: int = 100, max_nan_fraction: float = 0.2
) -> TreeBaseline:
    """ExtraTreesRegressor - documented reproduction-adjacent choice
    (command.md section 4/12.1), small n_estimators, fixed seed. Candidate
    columns with a high NaN rate are excluded (same fabrication concern as
    docs/decisions.md D7 for health.py's PCA HI)."""
    feature_columns = tuple(candidate_feature_columns(df_train, max_nan_fraction=max_nan_fraction))
    median_fill = df_train[list(feature_columns)].median().to_dict()
    x_train = df_train[list(feature_columns)].fillna(median_fill)
    y_train = df_train[TARGET_COLUMN]

    model = ExtraTreesRegressor(n_estimators=n_estimators, random_state=SEED, n_jobs=-1)
    model.fit(x_train, y_train)
    return TreeBaseline(feature_columns=feature_columns, model=model, median_fill=median_fill)


def predict_tree_baseline(df: pd.DataFrame, model: TreeBaseline) -> pd.Series:
    x = df[list(model.feature_columns)].fillna(model.median_fill)
    return pd.Series(model.model.predict(x), index=df.index)
