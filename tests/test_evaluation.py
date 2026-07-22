import numpy as np
import pandas as pd
import pytest

from bearing_pdm.evaluation import assert_no_leakage, college_walk_forward, leave_one_bearing_out_femto

N = 40


def _bearing_df(bearing_run_id: str, role: str, total_life_s: float, n: int = N, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    life = np.linspace(0, 1, n)
    elapsed_s = np.arange(n) * 10.0
    return pd.DataFrame({
        "bearing_run_id": bearing_run_id,
        "role": role,
        "sequence_index": np.arange(n),
        "event_timestamp": pd.Timestamp("1900-01-01") + pd.to_timedelta(elapsed_s, unit="s"),
        "rul_seconds": total_life_s - elapsed_s,
        "vibration_x_rms": 0.5 + 4.5 * life + rng.normal(0, 0.02, n),
        "vibration_x_kurtosis": -0.2 + 8.0 * life**2 + rng.normal(0, 0.05, n),
    })


def _femto_learning_df(n_bearings: int = 3) -> pd.DataFrame:
    return pd.concat(
        [_bearing_df(f"femto:BearingX_{i}", "learning", total_life_s=300.0 + 50 * i, seed=i) for i in range(n_bearings)],
        ignore_index=True,
    )


def test_assert_no_leakage_passes_for_learning_role():
    df = _femto_learning_df()
    assert_no_leakage(df, allowed_roles={"learning"})  # must not raise


def test_assert_no_leakage_raises_for_test_censored_role():
    df = _bearing_df("femto:Bearing1_3", "test_censored", total_life_s=300.0)
    with pytest.raises(ValueError, match="test_censored"):
        assert_no_leakage(df, allowed_roles={"learning"})


def test_assert_no_leakage_raises_for_full_test_role():
    df = _bearing_df("femto:Bearing1_3", "full_test", total_life_s=300.0)
    with pytest.raises(ValueError, match="full_test"):
        assert_no_leakage(df, allowed_roles={"learning"})


def test_leave_one_bearing_out_femto_covers_every_bearing_as_holdout():
    df = _femto_learning_df(n_bearings=3)
    results = leave_one_bearing_out_femto(df)

    held_out = set(results["held_out_bearing"])
    assert held_out == {"femto:BearingX_0", "femto:BearingX_1", "femto:BearingX_2"}
    assert set(results["model"]) == {"naive", "extra_trees"}
    assert len(results) == 3 * 2  # 3 bearings x 2 models
    assert (results["mae_seconds"] >= 0).all()


def test_leave_one_bearing_out_femto_refuses_hidden_roles():
    df = _bearing_df("femto:Bearing1_3", "test_censored", total_life_s=300.0)
    with pytest.raises(ValueError):
        leave_one_bearing_out_femto(df)


def test_college_walk_forward_is_chronological_and_produces_folds():
    df = _bearing_df("college:nsk6205", "college_run", total_life_s=1000.0, n=200)
    results = college_walk_forward(df, n_folds=4)

    assert set(results["model"]) == {"naive", "extra_trees"}
    assert results["fold"].nunique() == 3  # n_folds-1 test folds in an expanding-window scheme
    assert (results["mae_seconds"] >= 0).all()


def test_college_walk_forward_refuses_hidden_roles():
    df = _bearing_df("femto:Bearing1_3", "test_censored", total_life_s=300.0)
    with pytest.raises(ValueError):
        college_walk_forward(df)
