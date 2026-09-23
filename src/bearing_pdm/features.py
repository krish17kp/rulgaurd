"""Time-domain, frequency-domain, and temperature feature formulas.

Defaults match config/project.example.toml (frequency bands, kurtosis
form, sample rate). Every formula is NaN-in/NaN-out on degenerate input
(constant signal, all-missing window) rather than raising or fabricating
a value - consistent with the NaN-preservation policy in college.py /
femto.py (docs/decisions.md D6) and the "never fabricate" rule in
command.md. Callers decide what a NaN feature means downstream.

Kurtosis form: Fisher (excess), population moments (ddof=0) - matches
config/project.example.toml [kurtosis] form="fisher".
"""

from __future__ import annotations

import numpy as np

DEFAULT_FREQUENCY_BANDS_HZ: dict[str, tuple[float, float]] = {
    "low": (0.0, 1000.0),
    "mid": (1000.0, 5000.0),
    "high": (5000.0, 12800.0),
}


def _safe_divide(numerator: float, denominator: float) -> float:
    """NaN (not error, not 0) when the denominator is zero/degenerate."""
    if denominator == 0 or not np.isfinite(denominator):
        return float("nan")
    return numerator / denominator


def time_domain_features(x: np.ndarray, prefix: str) -> dict[str, float]:
    """14 time-domain stats (command.md section 10.4) for one 1D signal.

    NaN samples in x are dropped before computing (missing != zero). If
    every sample is NaN, every feature is NaN.
    """
    x = np.asarray(x, dtype="float64")
    x = x[~np.isnan(x)]

    if x.size == 0:
        keys = [
            "mean", "abs_mean", "rms", "std", "var", "min", "max", "peak_to_peak",
            "crest_factor", "shape_factor", "impulse_factor", "clearance_factor",
            "kurtosis", "skewness",
        ]
        return {f"{prefix}_{k}": float("nan") for k in keys}

    mean = float(np.mean(x))
    abs_mean = float(np.mean(np.abs(x)))
    rms = float(np.sqrt(np.mean(x**2)))
    std = float(np.std(x, ddof=0))
    var = std**2
    x_min = float(np.min(x))
    x_max = float(np.max(x))
    peak_to_peak = x_max - x_min
    abs_peak = float(np.max(np.abs(x)))
    sqrt_abs_mean = float(np.mean(np.sqrt(np.abs(x))))

    crest_factor = _safe_divide(abs_peak, rms)
    shape_factor = _safe_divide(rms, abs_mean)
    impulse_factor = _safe_divide(abs_peak, abs_mean)
    clearance_factor = _safe_divide(abs_peak, sqrt_abs_mean**2)

    if std == 0:
        kurtosis = float("nan")
        skewness = float("nan")
    else:
        kurtosis = float(np.mean((x - mean) ** 4) / std**4 - 3.0)  # Fisher (excess)
        skewness = float(np.mean((x - mean) ** 3) / std**3)

    values = {
        "mean": mean, "abs_mean": abs_mean, "rms": rms, "std": std, "var": var,
        "min": x_min, "max": x_max, "peak_to_peak": peak_to_peak,
        "crest_factor": crest_factor, "shape_factor": shape_factor,
        "impulse_factor": impulse_factor, "clearance_factor": clearance_factor,
        "kurtosis": kurtosis, "skewness": skewness,
    }
    return {f"{prefix}_{k}": v for k, v in values.items()}


def frequency_domain_features(
    x: np.ndarray,
    sample_rate_hz: float,
    prefix: str,
    bands_hz: dict[str, tuple[float, float]] | None = None,
) -> dict[str, float]:
    """FFT-based features over the real (one-sided) magnitude spectrum.

    NaN samples are dropped first (breaks even spacing - acceptable for
    this project's low NaN rate, see docs/dataset-audit.md; documented
    limitation, not silently wrong).
    """
    bands_hz = bands_hz or DEFAULT_FREQUENCY_BANDS_HZ
    x = np.asarray(x, dtype="float64")
    x = x[~np.isnan(x)]

    keys = [
        "dominant_frequency_hz", "spectral_centroid_hz", "spectral_entropy",
        "frequency_rms_hz", "total_spectral_energy",
    ] + [f"band_energy_frac_{name}" for name in bands_hz]

    if x.size < 2:
        return {f"{prefix}_{k}": float("nan") for k in keys}

    n = x.size
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate_hz)
    magnitude = np.abs(np.fft.rfft(x))
    power = magnitude**2

    # Exclude DC (bin 0) from dominant-frequency search - a nonzero mean
    # would otherwise always "win" and the feature would be meaningless.
    if len(freqs) > 1:
        ac_idx = np.argmax(magnitude[1:]) + 1
        dominant_frequency_hz = float(freqs[ac_idx])
    else:
        dominant_frequency_hz = float("nan")

    total_magnitude = float(np.sum(magnitude))
    spectral_centroid_hz = _safe_divide(float(np.sum(freqs * magnitude)), total_magnitude)

    total_power = float(np.sum(power))
    frequency_rms_hz = float(np.sqrt(_safe_divide(float(np.sum(freqs**2 * power)), total_power))) \
        if total_power > 0 else float("nan")

    if total_magnitude > 0:
        p = magnitude / total_magnitude
        p_nonzero = p[p > 0]
        spectral_entropy = float(-np.sum(p_nonzero * np.log2(p_nonzero)))
    else:
        spectral_entropy = float("nan")

    total_spectral_energy = total_power

    band_fracs = {}
    for name, (lo, hi) in bands_hz.items():
        mask = (freqs >= lo) & (freqs < hi)
        band_fracs[f"band_energy_frac_{name}"] = _safe_divide(float(np.sum(power[mask])), total_power)

    values = {
        "dominant_frequency_hz": dominant_frequency_hz,
        "spectral_centroid_hz": spectral_centroid_hz,
        "spectral_entropy": spectral_entropy,
        "frequency_rms_hz": frequency_rms_hz,
        "total_spectral_energy": total_spectral_energy,
        **band_fracs,
    }
    return {f"{prefix}_{k}": v for k, v in values.items()}


def temperature_features(temp: np.ndarray, prefix: str) -> dict[str, float]:
    """mean/min/max/std/slope for one temperature channel. Slope is a
    simple within-window/within-file linear fit against sample index
    (command.md: 'within-window or within-file slope'). Rolling trend
    across multiple windows/files is M3's job (health.py), not this
    single-window formula."""
    temp = np.asarray(temp, dtype="float64")
    valid = ~np.isnan(temp)
    t = temp[valid]

    if t.size == 0:
        return {f"{prefix}_{k}": float("nan") for k in ["mean", "min", "max", "std", "slope"]}

    mean = float(np.mean(t))
    t_min = float(np.min(t))
    t_max = float(np.max(t))
    std = float(np.std(t, ddof=0))

    if t.size >= 2:
        idx = np.nonzero(valid)[0].astype("float64")
        slope = float(np.polyfit(idx, t, 1)[0])
    else:
        slope = float("nan")

    return {
        f"{prefix}_mean": mean, f"{prefix}_min": t_min, f"{prefix}_max": t_max,
        f"{prefix}_std": std, f"{prefix}_slope": slope,
    }
