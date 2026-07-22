import numpy as np
import pandas as pd

from bearing_pdm.health import (
    NON_FEATURE_COLUMNS,
    apply_pca_hi,
    apply_transparent_hi,
    candidate_feature_columns,
    evaluate_hi,
    fit_pca_hi,
    fit_transparent_hi_baseline,
    monotonicity_trendability_scores,
)

N = 40  # per bearing


def _synthetic_degrading_df(n_bearings: int = 2, n: int = N, seed: int = 0) -> pd.DataFrame:
    """Two bearings, monotonically degrading RMS/kurtosis + a bunch of
    noisy irrelevant feature columns, so feature-selection has something
    real to select against."""
    rng = np.random.default_rng(seed)
    frames = []
    for b in range(n_bearings):
        life = np.linspace(0, 1, n)
        base = {
            "bearing_run_id": f"femto:BearingX_{b}",
            "role": "learning",
            "sequence_index": np.arange(n),
            "vibration_x_rms": 0.5 + 4.5 * life + rng.normal(0, 0.02, n),
            "vibration_y_rms": 0.4 + 4.0 * life + rng.normal(0, 0.02, n),
            "vibration_x_kurtosis": -0.2 + 8.0 * life**2 + rng.normal(0, 0.05, n),
            "vibration_y_kurtosis": -0.1 + 7.0 * life**2 + rng.normal(0, 0.05, n),
        }
        for j in range(10):
            base[f"noise_feature_{j}"] = rng.normal(0, 1, n)  # irrelevant, should rank low
        frames.append(pd.DataFrame(base))
    return pd.concat(frames, ignore_index=True)


def test_candidate_feature_columns_excludes_contract_fields():
    df = _synthetic_degrading_df()
    cols = candidate_feature_columns(df)
    assert "bearing_run_id" not in cols
    assert "sequence_index" not in cols
    assert "vibration_x_rms" in cols
    assert set(NON_FEATURE_COLUMNS) & set(cols) == set()


def test_transparent_hi_decreases_with_degradation():
    df = _synthetic_degrading_df()
    baseline = fit_transparent_hi_baseline(df, healthy_fraction=0.1)
    hi = apply_transparent_hi(df, baseline)

    assert hi.min() >= 0.0
    assert hi.max() <= 1.0
    # early rows (healthy) should score higher than late rows (degraded)
    assert hi.iloc[0] > hi.iloc[N - 1]
    assert hi.iloc[N] > hi.iloc[2 * N - 1]  # second bearing, same pattern


def test_transparent_hi_evaluate_shows_strong_negative_trend():
    df = _synthetic_degrading_df()
    baseline = fit_transparent_hi_baseline(df, healthy_fraction=0.1)
    hi = apply_transparent_hi(df, baseline)
    report = evaluate_hi(df, hi)

    assert len(report) == 2  # two bearings
    assert (report["monotonicity"] > 0.8).all()
    # 1/(1+anomaly) saturates for large anomaly, so Pearson correlation with a
    # linear time axis is necessarily weaker than monotonicity alone implies -
    # -0.5 still confirms a strong, consistent negative trend.
    assert (report["trend_corr"] < -0.5).all()


def test_monotonicity_trendability_ranks_real_features_above_noise():
    df = _synthetic_degrading_df()
    scores = monotonicity_trendability_scores(df, candidate_feature_columns(df))

    top_4 = set(scores.head(4).index)
    assert top_4 == {"vibration_x_rms", "vibration_y_rms", "vibration_x_kurtosis", "vibration_y_kurtosis"}
    for noise_col in [c for c in df.columns if c.startswith("noise_feature_")]:
        assert scores[noise_col] < scores["vibration_x_rms"]


def test_pca_hi_selects_degradation_features_and_orients_correctly():
    df = _synthetic_degrading_df()
    model = fit_pca_hi(df, top_k=4)

    assert set(model.selected_features) <= {
        "vibration_x_rms", "vibration_y_rms", "vibration_x_kurtosis", "vibration_y_kurtosis",
    }

    hi = apply_pca_hi(df, model)
    assert hi.iloc[0] > hi.iloc[N - 1]  # healthy > degraded, oriented correctly
    report = evaluate_hi(df, hi)
    assert (report["trend_corr"] < -0.5).all()


def test_pca_hi_excludes_columns_entirely_missing_for_some_bearings():
    df = _synthetic_degrading_df()
    # bearing_temp_mean: fully present for bearing 0, entirely absent for
    # bearing 1 (mirrors real Bearing2_2/Bearing3_2 with zero temp files).
    df["bearing_temp_mean"] = np.where(
        df["bearing_run_id"] == "femto:BearingX_0", 40.0 + 20.0 * (df["sequence_index"] / N), np.nan
    )
    model = fit_pca_hi(df, top_k=8)
    assert "bearing_temp_mean" not in model.selected_features


def test_candidate_feature_columns_nan_fraction_filter():
    df = _synthetic_degrading_df(n_bearings=1, n=10)
    df["half_missing"] = [1.0] * 5 + [np.nan] * 5
    cols_unfiltered = candidate_feature_columns(df)
    cols_filtered = candidate_feature_columns(df, max_nan_fraction=0.2)
    assert "half_missing" in cols_unfiltered
    assert "half_missing" not in cols_filtered


def test_pca_hi_frozen_model_applies_to_new_rows_without_refitting():
    df_train = _synthetic_degrading_df(seed=0)
    df_new = _synthetic_degrading_df(seed=1)  # different noise draw, same trend
    model = fit_pca_hi(df_train, top_k=4)

    hi_new = apply_pca_hi(df_new, model)
    assert len(hi_new) == len(df_new)
    assert hi_new.iloc[0] > hi_new.iloc[N - 1]


def test_fit_transparent_hi_baseline_guards_zero_std(monkeypatch):
    df = _synthetic_degrading_df(n_bearings=1, n=10)
    # Force a constant column so std would be exactly 0 for the healthy slice.
    df["vibration_x_rms"] = 1.0
    baseline = fit_transparent_hi_baseline(df, healthy_fraction=0.5)
    assert baseline.feature_stds["vibration_x_rms"] == 1.0  # guarded, not 0 -> no ZeroDivisionError
    hi = apply_transparent_hi(df, baseline)
    assert not hi.isna().any()
