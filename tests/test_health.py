import numpy as np
import pandas as pd
import pytest

from bearing_pdm.health import (
    NON_FEATURE_COLUMNS,
    apply_pca_hi,
    apply_reference_hi,
    apply_transparent_hi,
    candidate_feature_columns,
    evaluate_hi,
    fit_pca_hi,
    fit_reference_hi,
    fit_transparent_hi_baseline,
    monotonicity_trendability_scores,
    reference_hi_diagnostics,
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
    assert (report["spearman"] < -0.5).all()


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
    assert (report["spearman"] < -0.5).all()


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


# ---------------------------------------------------------------------------
# Reference HI (docs/decisions.md D18)
#
# These protect the defect that blocked M5: on the real FEMTO learning set the
# transparent HI pinned 47.5% of all acquisitions at exactly 1.0 (87.4% of
# Bearing3_1, 88.9% of Bearing3_2, both with an interquartile range of 0.00),
# because a hard floor at 0 was combined with a healthy reference pooled across
# three different operating conditions.
# ---------------------------------------------------------------------------

REF_N = 200  # per bearing; must exceed REFERENCE_HI_SKIP + REFERENCE_HI_N


def _reference_df(
    n_bearings: int = 2, n: int = REF_N, seed: int = 0, level_offsets: tuple[float, ...] = (0.0, 0.0)
) -> pd.DataFrame:
    """Bearings that stay flat then degrade late (FEMTO's measured
    flat-then-cliff shape), each optionally sitting at a different absolute
    vibration level - the operating-condition difference that broke the pooled
    reference."""
    rng = np.random.default_rng(seed)
    frames = []
    for b in range(n_bearings):
        life = np.linspace(0, 1, n)
        ramp = np.clip((life - 0.6) / 0.4, 0, 1) ** 2
        offset = level_offsets[b % len(level_offsets)]
        frames.append(pd.DataFrame({
            "bearing_run_id": f"femto:BearingX_{b}",
            "role": "learning",
            "sequence_index": np.arange(n),
            "rul_seconds": (n - 1 - np.arange(n)) * 10.0,
            "vibration_x_rms": offset + 0.40 + 2.0 * ramp + rng.normal(0, 0.005, n),
            "vibration_y_rms": offset + 0.35 + 1.8 * ramp + rng.normal(0, 0.005, n),
            "vibration_x_peak_to_peak": 4 * offset + 3.0 + 14.0 * ramp + rng.normal(0, 0.02, n),
            "vibration_y_peak_to_peak": 4 * offset + 2.8 + 12.0 * ramp + rng.normal(0, 0.02, n),
            "vibration_x_kurtosis": 0.05 + 6.0 * ramp + rng.normal(0, 0.01, n),
            "vibration_y_kurtosis": 0.04 + 5.0 * ramp + rng.normal(0, 0.01, n),
            "vibration_x_crest_factor": 3.7 + 2.5 * ramp + rng.normal(0, 0.01, n),
            "vibration_y_crest_factor": 3.6 + 2.3 * ramp + rng.normal(0, 0.01, n),
        }))
    return pd.concat(frames, ignore_index=True)


def test_reference_hi_never_pins_at_zero_or_one():
    """The regression test for the blocker. The logistic map puts HI in the
    OPEN interval (0, 1), so pinning is structurally impossible rather than
    clipped away."""
    df = _reference_df()
    hi = apply_reference_hi(df, fit_reference_hi(df))

    assert (hi > 0.0).all(), "HI hit exactly 0 - the mapping is clipping, not saturating"
    assert (hi < 1.0).all(), "HI hit exactly 1.0 - this is the D18 pinning defect returning"
    assert hi.iloc[0] > hi.iloc[REF_N - 1]  # healthy start, degraded end


def test_reference_hi_is_immune_to_a_per_bearing_level_offset():
    """Two bearings with identical degradation shape but different absolute
    vibration level must get near-identical HI curves. Under the old pooled
    reference the lower-level bearing pinned at 1.0 for most of its life."""
    df = _reference_df(level_offsets=(0.0, 0.6))
    hi = apply_reference_hi(df, fit_reference_hi(df))

    curve_a = hi.iloc[:REF_N].to_numpy()
    curve_b = hi.iloc[REF_N:].to_numpy()
    assert np.max(np.abs(curve_a - curve_b)) < 0.05

    # And specifically: the offset bearing is not stuck at either rail.
    assert curve_b.max() < 0.999
    assert curve_b.min() > 0.001


def test_reference_hi_does_not_depend_on_total_run_length():
    """The healthy reference is a fixed COUNT of leading acquisitions, not a
    fraction of total life. Total life is only known after failure, so a
    fraction cannot be computed online or on a censored bearing."""
    df = _reference_df(n_bearings=1)
    model = fit_reference_hi(_reference_df())

    full = apply_reference_hi(df, model).to_numpy()
    half = apply_reference_hi(df.iloc[: REF_N // 2].copy(), model).to_numpy()

    np.testing.assert_allclose(full[: REF_N // 2], half, rtol=0, atol=0)


def test_reference_hi_is_causal():
    """HI at row i must not change when every row after i is deleted - a direct
    assertion that no future information reaches the value."""
    df = _reference_df(n_bearings=1)
    model = fit_reference_hi(_reference_df())

    full = apply_reference_hi(df, model).to_numpy()
    for cut in (80, 120, 199):
        truncated = apply_reference_hi(df.iloc[: cut + 1].copy(), model).to_numpy()
        assert truncated[cut] == full[cut]


def test_reference_hi_is_robust_to_shuffled_row_order():
    """The trailing rolling smoother must key off sequence_index, not row
    position. A caller that hands rows out of chronological order (or with
    bearings interleaved) must get the same per-acquisition HI back, not a
    value contaminated by whatever order the rows happened to arrive in."""
    df = _reference_df()
    model = fit_reference_hi(_reference_df())

    chronological = apply_reference_hi(df, model)

    shuffled_df = df.sample(frac=1.0, random_state=7)
    shuffled_hi = apply_reference_hi(shuffled_df, model)

    aligned = shuffled_hi.reindex(df.index)
    np.testing.assert_allclose(aligned.to_numpy(), chronological.to_numpy(), rtol=0, atol=1e-12)


def test_reference_hi_survives_a_joblib_round_trip(tmp_path):
    import joblib

    df = _reference_df()
    model = fit_reference_hi(df)
    path = tmp_path / "reference_hi.joblib"
    joblib.dump(model, path)

    np.testing.assert_allclose(
        apply_reference_hi(df, joblib.load(path)).to_numpy(),
        apply_reference_hi(df, model).to_numpy(),
        rtol=0, atol=0,
    )


def test_reference_hi_refuses_to_fit_on_hidden_roles():
    """docs/data-contract.md: test_censored / full_test rows are never fit on."""
    df = _reference_df()
    df.loc[df.index[:10], "role"] = "test_censored"
    with pytest.raises(ValueError, match="Refusing to fit"):
        fit_reference_hi(df)


def test_reference_hi_applies_to_a_censored_prefix_with_no_labels():
    """The censored FEMTO bearings have rul_seconds = NaN by construction. The
    HI must still produce a finite value for every row, since it never reads
    the target."""
    model = fit_reference_hi(_reference_df())
    censored = _reference_df(n_bearings=1, seed=7)
    censored["role"] = "test_censored"
    censored["rul_seconds"] = np.nan

    hi = apply_reference_hi(censored, model)
    assert hi.notna().all()
    assert ((hi > 0.0) & (hi < 1.0)).all()


def test_reference_hi_rejects_a_single_extreme_outlier():
    """One 100x kurtosis spike must not move the HI much - the robust scale and
    the trailing rolling median exist to stop exactly that. The old pooled std
    of vibration_y_kurtosis was 15.34 against a mean of 2.12."""
    df = _reference_df(n_bearings=1)
    model = fit_reference_hi(_reference_df())
    clean = apply_reference_hi(df, model).to_numpy()

    spiked = df.copy()
    spiked.loc[spiked.index[100], "vibration_x_kurtosis"] *= 100.0
    contaminated = apply_reference_hi(spiked, model).to_numpy()

    assert np.max(np.abs(contaminated - clean)) < 0.1


def test_derived_health_outputs_can_never_become_rul_features():
    """If the HI is ever persisted alongside the features, it must not enter the
    RUL feature matrix - that would be a target-derived feature."""
    df = _reference_df(n_bearings=1)
    df["health_indicator"] = apply_reference_hi(df, fit_reference_hi(_reference_df()))
    df["hi_degradation_score"] = 0.0

    cols = candidate_feature_columns(df)
    assert "health_indicator" not in cols
    assert "hi_degradation_score" not in cols
    assert "vibration_x_rms" in cols


def test_reference_hi_diagnostics_reports_the_pinning_guards():
    df = _reference_df()
    report = reference_hi_diagnostics(df, apply_reference_hi(df, fit_reference_hi(df)))

    assert len(report) == 2
    assert (report["pct_at_one"] == 0.0).all()
    assert (report["pct_at_zero"] == 0.0).all()
    assert (report["spearman"] < -0.5).all()
    assert (report["hi_healthy_window"] > report["hi_final_1pct"]).all()
