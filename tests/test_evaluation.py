import numpy as np
import pandas as pd
import pytest

from bearing_pdm.evaluation import (
    assert_no_leakage,
    college_walk_forward,
    leave_one_bearing_out_femto,
    phm2012_score,
    score_hidden_set,
    summarize_hidden_set,
)
from bearing_pdm.modeling import fit_naive_baseline, predict_naive_baseline

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


# ---------------------------------------------------------------------------
# Hidden-set scoring (docs/decisions.md D16)
# ---------------------------------------------------------------------------


def _censored_df(labels=("Bearing1_3", "Bearing2_7"), n: int = 30) -> pd.DataFrame:
    return pd.concat(
        [_bearing_df(f"femto:{lab}", "test_censored", total_life_s=float("nan"), n=n, seed=i)
         for i, lab in enumerate(labels)],
        ignore_index=True,
    )


def _constant_predictor(value: float):
    return lambda frame: pd.Series([value] * len(frame), index=frame.index)


def test_score_hidden_set_predicts_at_the_last_censored_acquisition():
    """The convention is one prediction per bearing, at the END of the prefix -
    not one per acquisition. Getting this wrong silently changes the benchmark."""
    df = _censored_df(n=30)
    # Predictor echoes sequence_index, so the scored value reveals which row was used.
    scored = score_hidden_set(
        df,
        {"Bearing1_3": 1000.0, "Bearing2_7": 500.0},
        {"echo": lambda frame: frame["sequence_index"].astype(float)},
    )

    assert len(scored) == 2, "expected exactly one scored point per bearing"
    assert set(scored["predicted_rul_seconds"]) == {29.0}, "must use the LAST acquisition"
    assert scored["n_censored_acquisitions"].tolist() == [30, 30]


def test_score_hidden_set_error_sign_marks_overestimates():
    """error_seconds > 0 must mean 'predicted MORE life than actual' - the
    unsafe direction - and percent_error must carry the opposite sign."""
    df = _censored_df(labels=("Bearing1_3",))
    scored = score_hidden_set(df, {"Bearing1_3": 1000.0}, {"m": _constant_predictor(1500.0)})

    row = scored.iloc[0]
    assert row["error_seconds"] == 500.0
    assert row["percent_error"] == -50.0


def test_score_hidden_set_refuses_non_censored_rows():
    """Scoring learning rows here would silently be an in-sample result."""
    df = _bearing_df("femto:Bearing1_1", "learning", total_life_s=300.0)
    with pytest.raises(ValueError, match="test_censored"):
        score_hidden_set(df, {"Bearing1_1": 100.0}, {"m": _constant_predictor(1.0)})


def test_score_hidden_set_records_condition_id():
    df = _censored_df(labels=("Bearing1_3", "Bearing2_7"))
    scored = score_hidden_set(
        df, {"Bearing1_3": 1000.0, "Bearing2_7": 500.0}, {"m": _constant_predictor(1.0)}
    )
    assert dict(zip(scored["bearing"], scored["condition_id"])) == {"Bearing1_3": 1, "Bearing2_7": 2}


def test_score_hidden_set_gives_the_real_naive_baseline_history_to_compute_elapsed_time():
    """Regression test for the bug where score_hidden_set passed the naive
    baseline only the LAST censored row. NaiveBaseline has no start-time entry
    for a hidden bearing (it was never in the training set), so it falls back
    to the group-min timestamp of whatever frame it is given
    (modeling._elapsed_seconds). A one-row frame's group-min is its own
    timestamp, so elapsed collapsed to 0 and every bearing's naive prediction
    became the same constant (mean_total_life_seconds) regardless of how far
    into its own censored prefix it actually was.

    Two hidden bearings with different-length censored prefixes must therefore
    get DIFFERENT naive predictions, and each must be less than the bare
    training mean (since each has nonzero elapsed time to subtract)."""
    train_df = _femto_learning_df(n_bearings=3)
    naive_model = fit_naive_baseline(train_df)

    # Same construction, but Bearing2_7's censored prefix runs far longer than
    # Bearing1_3's - a real naive baseline must read that difference.
    df = pd.concat(
        [_censored_df(labels=("Bearing1_3",), n=5), _censored_df(labels=("Bearing2_7",), n=50)],
        ignore_index=True,
    )

    scored = score_hidden_set(
        df,
        {"Bearing1_3": 100000.0, "Bearing2_7": 100000.0},
        {"naive": lambda frame: predict_naive_baseline(frame, naive_model)},
    )

    predictions = dict(zip(scored["bearing"], scored["predicted_rul_seconds"]))
    assert predictions["Bearing1_3"] != predictions["Bearing2_7"], (
        "naive predictions for bearings with different elapsed censored history "
        "must differ - identical values means elapsed time collapsed to 0 again"
    )
    assert predictions["Bearing1_3"] < naive_model.mean_total_life_seconds
    assert predictions["Bearing2_7"] < naive_model.mean_total_life_seconds


def test_summarize_hidden_set_counts_overestimates_separately():
    df = _censored_df(labels=("Bearing1_3", "Bearing2_7"))
    # actual 1000 and 500; constant prediction 800 -> one under, one over.
    scored = score_hidden_set(
        df, {"Bearing1_3": 1000.0, "Bearing2_7": 500.0}, {"m": _constant_predictor(800.0)}
    )
    summary = summarize_hidden_set(scored)["m"]

    assert summary["n_bearings"] == 2
    assert summary["n_overestimates"] == 1
    assert summary["mae_seconds"] == pytest.approx((200 + 300) / 2)
    assert summary["rmse_seconds"] == pytest.approx(np.sqrt((200**2 + 300**2) / 2))


# ---------------------------------------------------------------------------
# Official PHM 2012 scoring function (docs/decisions.md D17)
# ---------------------------------------------------------------------------


def test_phm2012_score_reproduces_the_official_figure_annotations():
    """The two points printed on the official challenge figure. If either of
    these moves, the constants or the branch split are wrong."""
    assert phm2012_score(-10.0) == pytest.approx(0.25)
    assert phm2012_score(20.0) == pytest.approx(0.50)


def test_phm2012_score_is_one_at_zero_error_and_continuous_there():
    assert phm2012_score(0.0) == pytest.approx(1.0)
    assert phm2012_score(-1e-9) == pytest.approx(1.0)
    assert phm2012_score(1e-9) == pytest.approx(1.0)


def test_phm2012_score_punishes_overestimates_harder_than_underestimates():
    """The asymmetry is the point of the metric and the easiest thing to invert.
    Er <= 0 is an OVER-estimate (predicted more life than actual, late warning,
    dangerous); Er > 0 is an UNDER-estimate (early warning, safe)."""
    over, under = phm2012_score(-20.0), phm2012_score(20.0)
    assert over < under
    assert over == pytest.approx(2.0 ** (-20.0 / 5.0))
    assert under == pytest.approx(2.0 ** (-20.0 / 20.0))


def test_phm2012_score_stays_in_unit_interval_and_decays_steeply():
    for er in [-500.0, -100.0, -50.0, -5.0, 0.0, 5.0, 50.0, 100.0, 500.0]:
        assert 0.0 < phm2012_score(er) <= 1.0
    assert phm2012_score(-50.0) == pytest.approx(0.000977, abs=1e-6)


def test_score_hidden_set_attaches_a_phm2012_score_per_bearing():
    df = _censored_df(labels=("Bearing1_3",))
    # actual 1000, predicted 1100 -> Er = -10 -> A = 0.25
    scored = score_hidden_set(df, {"Bearing1_3": 1000.0}, {"m": _constant_predictor(1100.0)})
    assert scored.iloc[0]["phm2012_score"] == pytest.approx(0.25)
    assert summarize_hidden_set(scored)["m"]["phm2012_score"] == pytest.approx(0.25)
