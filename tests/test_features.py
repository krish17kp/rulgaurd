import math

import numpy as np
import pytest

from bearing_pdm.features import (
    frequency_domain_features,
    temperature_features,
    time_domain_features,
)


def test_time_domain_hand_computed_values():
    x = np.array([1.0, -1.0, 2.0, -2.0])
    feats = time_domain_features(x, prefix="v")

    assert feats["v_mean"] == pytest.approx(0.0)
    assert feats["v_abs_mean"] == pytest.approx(1.5)
    assert feats["v_rms"] == pytest.approx(math.sqrt((1 + 1 + 4 + 4) / 4))
    assert feats["v_min"] == -2.0
    assert feats["v_max"] == 2.0
    assert feats["v_peak_to_peak"] == 4.0
    # population std: sqrt(mean((x-mean)^2)) = sqrt((1+1+4+4)/4) = sqrt(2.5)
    assert feats["v_std"] == pytest.approx(math.sqrt(2.5))
    assert feats["v_var"] == pytest.approx(2.5)


def test_time_domain_constant_nonzero_signal_ratios_defined_kurtosis_nan():
    x = np.full(10, 5.0)
    feats = time_domain_features(x, prefix="v")

    assert feats["v_mean"] == 5.0
    assert feats["v_std"] == 0.0
    assert feats["v_crest_factor"] == pytest.approx(1.0)
    assert feats["v_shape_factor"] == pytest.approx(1.0)
    assert feats["v_impulse_factor"] == pytest.approx(1.0)
    assert feats["v_clearance_factor"] == pytest.approx(1.0)
    # kurtosis/skewness require std != 0 - must be NaN, not raise, not 0.
    assert math.isnan(feats["v_kurtosis"])
    assert math.isnan(feats["v_skewness"])


def test_time_domain_all_zero_signal_ratios_are_nan():
    x = np.zeros(10)
    feats = time_domain_features(x, prefix="v")

    assert feats["v_mean"] == 0.0
    assert feats["v_peak_to_peak"] == 0.0
    # 0/0 ratio features must be NaN, never silently 0 or 1.
    assert math.isnan(feats["v_crest_factor"])
    assert math.isnan(feats["v_shape_factor"])
    assert math.isnan(feats["v_impulse_factor"])
    assert math.isnan(feats["v_clearance_factor"])
    assert math.isnan(feats["v_kurtosis"])
    assert math.isnan(feats["v_skewness"])


def test_time_domain_empty_after_nan_drop_returns_all_nan():
    x = np.array([np.nan, np.nan, np.nan])
    feats = time_domain_features(x, prefix="v")
    assert all(math.isnan(v) for v in feats.values())
    assert len(feats) == 14


def test_time_domain_nan_values_are_dropped_not_zero_filled():
    x = np.array([1.0, 2.0, 3.0, np.nan, np.nan])
    feats = time_domain_features(x, prefix="v")
    # Mean of [1,2,3], NOT mean of [1,2,3,0,0].
    assert feats["v_mean"] == pytest.approx(2.0)


def test_frequency_domain_dominant_frequency_matches_synthetic_sine():
    sample_rate_hz = 25600.0
    n = 2560
    t = np.arange(n) / sample_rate_hz
    true_freq_hz = 500.0  # falls on an exact FFT bin: 25600/2560 = 10 Hz/bin
    x = 3.0 * np.sin(2 * np.pi * true_freq_hz * t)

    feats = frequency_domain_features(x, sample_rate_hz, prefix="v")

    assert feats["v_dominant_frequency_hz"] == pytest.approx(true_freq_hz, abs=10.0)


def test_frequency_domain_band_energy_fractions_sum_to_one():
    sample_rate_hz = 25600.0
    n = 2560
    t = np.arange(n) / sample_rate_hz
    x = np.sin(2 * np.pi * 500.0 * t) + 0.5 * np.sin(2 * np.pi * 3000.0 * t)

    feats = frequency_domain_features(x, sample_rate_hz, prefix="v")

    band_fracs = [v for k, v in feats.items() if k.startswith("v_band_energy_frac_")]
    assert sum(band_fracs) == pytest.approx(1.0, abs=1e-6)


def test_frequency_domain_too_short_signal_returns_nan():
    feats = frequency_domain_features(np.array([1.0]), 25600.0, prefix="v")
    assert all(math.isnan(v) for v in feats.values())


def test_temperature_features_hand_computed():
    temp = np.array([40.0, 42.0, 44.0, 46.0])
    feats = temperature_features(temp, prefix="bearing_temp")

    assert feats["bearing_temp_mean"] == pytest.approx(43.0)
    assert feats["bearing_temp_min"] == 40.0
    assert feats["bearing_temp_max"] == 46.0
    assert feats["bearing_temp_slope"] == pytest.approx(2.0)  # +2 degC per sample


def test_temperature_features_drops_nan_before_slope():
    temp = np.array([40.0, np.nan, 44.0, 46.0])
    feats = temperature_features(temp, prefix="bearing_temp")
    assert not math.isnan(feats["bearing_temp_mean"])
    assert feats["bearing_temp_mean"] == pytest.approx((40.0 + 44.0 + 46.0) / 3)


def test_temperature_features_all_nan_returns_nan():
    temp = np.array([np.nan, np.nan])
    feats = temperature_features(temp, prefix="bearing_temp")
    assert all(math.isnan(v) for v in feats.values())
