"""RUL regression baselines (command.md section 12.1).

Required: naive baseline, one tree-based baseline (ExtraTreesRegressor).
Small, documented hyperparameters - no broad search (command.md section
26.7: "the first review objective is a valid baseline, not the best
possible score").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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
    df_train: pd.DataFrame, n_estimators: int = 100, max_nan_fraction: float = 0.2,
    feature_columns: list[str] | None = None, target: str = TARGET_COLUMN,
    sample_weight: np.ndarray | None = None,
) -> TreeBaseline:
    """ExtraTreesRegressor - documented reproduction-adjacent choice
    (command.md section 4/12.1), small n_estimators, fixed seed. Candidate
    columns with a high NaN rate are excluded (same fabrication concern as
    docs/decisions.md D7 for health.py's PCA HI).

    `feature_columns` pins an explicit feature list/order (the cross-dataset
    experiments pin the frozen model's 44 columns so a refit is the same model);
    `target`/`sample_weight` serve the life-fraction model below."""
    if feature_columns is None:
        feature_columns = candidate_feature_columns(df_train, max_nan_fraction=max_nan_fraction)
    feature_columns = tuple(feature_columns)
    median_fill = df_train[list(feature_columns)].median().to_dict()
    x_train = df_train[list(feature_columns)].fillna(median_fill)
    y_train = df_train[target]

    model = ExtraTreesRegressor(n_estimators=n_estimators, random_state=SEED, n_jobs=-1)
    model.fit(x_train, y_train, sample_weight=sample_weight)
    return TreeBaseline(feature_columns=feature_columns, model=model, median_fill=median_fill)


def predict_tree_baseline(df: pd.DataFrame, model: TreeBaseline) -> pd.Series:
    x = df[list(model.feature_columns)].fillna(model.median_fill)
    return pd.Series(model.model.predict(x), index=df.index)


# ---------------------------------------------------------------------------
# Life-fraction target (cross-domain model, docs/cross-dataset.md)
# ---------------------------------------------------------------------------

LIFE_FRACTION_COLUMN = "life_fraction"
# A predicted fraction below this is floored before converting to seconds:
# elapsed * (1 - f) / f diverges as f -> 0.
MIN_LIFE_FRACTION = 0.05


def bearing_balanced_weights(df: pd.DataFrame) -> np.ndarray:
    """1 / (rows of that bearing): every training bearing gets equal total
    weight. Recording counts differ 150x across datasets (XJTU Bearing2_4: 42,
    IMS test 3: 6,324) - unweighted, the longest record would define the model."""
    counts = df["bearing_run_id"].map(df["bearing_run_id"].value_counts())
    return (1.0 / counts).to_numpy(dtype=float)


def fraction_to_rul(life_fraction: np.ndarray, elapsed_s: np.ndarray) -> np.ndarray:
    """RUL (s) implied by a life-fraction estimate at a known elapsed time:
    total = elapsed / f, so RUL = elapsed * (1 - f) / f.

    Elapsed time since installation is known online (the naive baseline uses it
    too); f is predicted from self-normalised features only - elapsed never
    enters the feature matrix (health.NON_FEATURE_COLUMNS). Exact when f is
    exact, but convex and divergent as f -> 0, so a small error in an early-life
    fraction becomes a large error in seconds. That is why cross-domain skill is
    judged in life-fraction units first (docs/decisions.md D24, which also
    records the rejected log-ratio target).
    """
    f = np.clip(np.asarray(life_fraction, dtype=float), MIN_LIFE_FRACTION, 1.0)
    return np.asarray(elapsed_s, dtype=float) * (1.0 - f) / f
