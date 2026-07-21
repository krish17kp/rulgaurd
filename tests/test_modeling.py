import numpy as np
import pandas as pd
import pytest

from bearing_pdm.modeling import (
    fit_naive_baseline,
    fit_tree_baseline,
    predict_naive_baseline,
    predict_tree_baseline,
)

N = 30


def _synthetic_rul_df(bearing_run_id: str = "femto:BearingX_0", n: int = N, total_life_s: float = 290.0, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    life = np.linspace(0, 1, n)
    elapsed_s = np.arange(n) * 10.0  # FEMTO-like 10s cadence
    return pd.DataFrame({
        "bearing_run_id": bearing_run_id,
        "role": "learning",
        "sequence_index": np.arange(n),
        "event_timestamp": pd.Timestamp("1900-01-01") + pd.to_timedelta(elapsed_s, unit="s"),
        "rul_seconds": total_life_s - elapsed_s,
        "vibration_x_rms": 0.5 + 4.5 * life + rng.normal(0, 0.02, n),
        "vibration_x_kurtosis": -0.2 + 8.0 * life**2 + rng.normal(0, 0.05, n),
    })


def test_fit_naive_baseline_uses_mean_total_life():
    df = pd.concat([
        _synthetic_rul_df("b1", total_life_s=290.0),
        _synthetic_rul_df("b2", total_life_s=490.0, seed=1),
    ], ignore_index=True)

    model = fit_naive_baseline(df)

    assert model.mean_total_life_seconds == 390.0  # (290+490)/2


def test_predict_naive_baseline_decreases_with_elapsed_time():
    df = _synthetic_rul_df(total_life_s=290.0)
    model = fit_naive_baseline(df)
    pred = predict_naive_baseline(df, model)

    assert pred.iloc[0] == 290.0  # elapsed 0
    assert pred.iloc[1] == 280.0  # elapsed 10s
    assert (pred.diff().dropna() < 0).all()  # strictly decreasing
    assert (pred >= 0).all()  # clipped at zero


def test_predict_naive_baseline_clips_at_zero_past_training_life():
    df = _synthetic_rul_df(total_life_s=50.0, n=20)  # elapsed exceeds 50s well before row 20
    model = fit_naive_baseline(df)
    pred = predict_naive_baseline(df, model)
    assert pred.iloc[-1] == 0.0


def test_predict_naive_baseline_uses_true_bearing_start_not_slice_start():
    # Regression test for docs/decisions.md D9: predicting on a mid-run
    # slice (like a later college walk-forward fold) must compute elapsed
    # time relative to the bearing's TRUE start (captured at fit time), not
    # relative to the first row of whatever slice is passed to predict().
    df = _synthetic_rul_df(total_life_s=290.0, n=30)
    model = fit_naive_baseline(df)  # fit on the full trajectory (elapsed 0..290s)

    mid_run_slice = df.iloc[10:15].reset_index(drop=True)  # starts at true elapsed=100s
    pred = predict_naive_baseline(mid_run_slice, model)

    # True elapsed at slice row 0 is 100s (row 10 * 10s), NOT 0s.
    assert pred.iloc[0] == pytest.approx(290.0 - 100.0)


def test_predict_naive_baseline_falls_back_for_unseen_bearing():
    df_train = _synthetic_rul_df("b1", total_life_s=290.0)
    model = fit_naive_baseline(df_train)

    df_new_bearing = _synthetic_rul_df("b2", total_life_s=490.0, seed=2)
    pred = predict_naive_baseline(df_new_bearing, model)

    # b2 wasn't in training, so elapsed falls back to b2's own slice-min
    # (its true start, since this is its full trajectory) - not an error.
    assert pred.iloc[0] == 290.0  # model's mean_total_life, elapsed=0


def test_tree_baseline_predicts_reasonable_rul_and_excludes_high_nan_columns():
    df = _synthetic_rul_df(total_life_s=290.0)
    df["mostly_missing"] = [1.0] * 5 + [np.nan] * (N - 5)  # >20% NaN

    model = fit_tree_baseline(df)

    assert "mostly_missing" not in model.feature_columns
    pred = predict_tree_baseline(df, model)
    assert len(pred) == N
    # trained-and-predicted-on-same-data sanity: predictions should track
    # the true target reasonably (not testing generalization here, that's
    # evaluation.py's leave-one-bearing-out job).
    assert abs(pred.iloc[0] - df["rul_seconds"].iloc[0]) < 100
