"""Synthetic bearing degradation simulator - SYNTHETIC / SIMULATED DATA.

Generates a reproducible sequence of two-axis vibration acquisitions with a
configurable gradual degradation (rising amplitude, rising impulsiveness via
periodic defect-like impacts, optional temperature drift). This is a
controlled demonstration signal, never a model of a real bearing and never
usable as evidence of real-world accuracy (ml-data.md: no claim here may be
read as validating the FEMTO model on real data). Every acquisition carries
the same two-column `vibration_x`/`vibration_y` shape the project's
`features.py` formulas already consume, so the existing feature-extraction
and applicability code is reused unmodified - no parallel analysis path.

Reproducibility: generation is a pure function of
(SyntheticConfig, acquisition_index) via a per-acquisition
`np.random.default_rng(seed, acquisition_index)` style derivation, so the
same config/seed always reproduces byte-identical signals.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

DATASET_LABEL = "SYNTHETIC"  # never presented as real data anywhere downstream


@dataclass(frozen=True)
class SyntheticConfig:
    seed: int = 42
    n_acquisitions: int = 20
    samples_per_acquisition: int = 2560
    sample_rate_hz: float = 25_600.0
    shaft_freq_hz: float = 50.0
    n_harmonics: int = 3
    baseline_noise_std: float = 0.05
    final_amplitude_multiplier: float = 6.0        # amplitude at the last acquisition vs the first
    final_impact_rate_multiplier: float = 8.0      # defect-impact rate at the last acquisition vs the first
    temperature_drift_c: float = 0.0               # 0 disables the optional temperature channel


def _acquisition_rng(cfg: SyntheticConfig, index: int) -> np.random.Generator:
    """Deterministic per-acquisition generator: same (seed, index) always
    gives the same stream, independent of how many acquisitions came before -
    the reproducibility test generates a single acquisition in isolation and
    must get the same bytes as generating the whole sequence."""
    return np.random.default_rng([cfg.seed, index])


def _degradation_fraction(index: int, n_acquisitions: int) -> float:
    """0.0 at the first acquisition, 1.0 at the last."""
    if n_acquisitions <= 1:
        return 1.0
    return index / (n_acquisitions - 1)


def generate_acquisition(cfg: SyntheticConfig, index: int) -> tuple[np.ndarray, np.ndarray]:
    """One (vibration_x, vibration_y) pair, shape (samples_per_acquisition,) each."""
    rng = _acquisition_rng(cfg, index)
    n = cfg.samples_per_acquisition
    t = np.arange(n) / cfg.sample_rate_hz
    frac = _degradation_fraction(index, cfg.n_acquisitions)
    amplitude = 1.0 + frac * (cfg.final_amplitude_multiplier - 1.0)

    def _axis(phase_offset: float) -> np.ndarray:
        # Base sinusoid stays at roughly constant amplitude (a healthy
        # bearing's rotating-frequency content does not itself grow); only
        # the impacts below grow with degradation, which is what should
        # drive both RMS and kurtosis up together.
        signal = np.zeros(n)
        for h in range(1, cfg.n_harmonics + 1):
            signal += (1.0 / h) * np.sin(2 * np.pi * cfg.shaft_freq_hz * h * t + phase_offset)
        signal += rng.normal(0.0, cfg.baseline_noise_std, size=n)

        impact_rate_hz = cfg.shaft_freq_hz * (
            1.0 + frac * (cfg.final_impact_rate_multiplier - 1.0)
        )
        mean_gap = cfg.sample_rate_hz / impact_rate_hz if impact_rate_hz > 0 else n + 1
        impact_positions = []
        pos = rng.exponential(mean_gap)
        while pos < n:
            impact_positions.append(pos)
            pos += rng.exponential(mean_gap)
        idx = np.arange(n)
        # A sharp, short-lived pulse per impact (not a broad decaying tail
        # that blends into the continuous signal) - this is what makes
        # impacts show up as kurtosis/impulsiveness rather than just energy.
        pulse_width_samples = max(1.0, cfg.sample_rate_hz / (cfg.shaft_freq_hz * 20))
        for pos in impact_positions:
            gauss_pulse = np.exp(-0.5 * ((idx - pos) / pulse_width_samples) ** 2)
            signal += amplitude * gauss_pulse * np.sin(2 * np.pi * (cfg.shaft_freq_hz * 4) * t)
        return signal

    x = _axis(0.0)
    y = _axis(np.pi / 4)
    return x, y


def generate_sequence(cfg: SyntheticConfig) -> list[tuple[np.ndarray, np.ndarray]]:
    return [generate_acquisition(cfg, i) for i in range(cfg.n_acquisitions)]


def write_synthetic_zip(cfg: SyntheticConfig, zip_path: str | Path) -> Path:
    """synthetic_bearing.zip: metadata.json (full config, clearly labelled
    SYNTHETIC) plus one acc_NNNNN.csv per acquisition - no header, two
    columns (vibration_x, vibration_y), matching the shape features.py's
    time_domain_features/frequency_domain_features already consume."""
    zip_path = Path(zip_path)
    sequence = generate_sequence(cfg)
    with zipfile.ZipFile(zip_path, "w") as zf:
        metadata = {"dataset_label": DATASET_LABEL, "config": asdict(cfg)}
        zf.writestr("metadata.json", json.dumps(metadata, indent=2))
        for i, (x, y) in enumerate(sequence):
            rows = "\n".join(f"{xv},{yv}" for xv, yv in zip(x, y, strict=True))
            zf.writestr(f"acc_{i:05d}.csv", rows + "\n")
    return zip_path
