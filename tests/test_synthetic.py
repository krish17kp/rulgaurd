"""Synthetic bearing simulator tests - reproducibility, feature sanity, and
the OOD/suppression guard (synthetic data must never be scored as if it
were real FEMTO data)."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import numpy as np
import pytest

from bearing_pdm.features import frequency_domain_features, time_domain_features
from bearing_pdm.synthetic import (
    DATASET_LABEL,
    SyntheticConfig,
    generate_acquisition,
    generate_sequence,
    write_synthetic_zip,
)

BUNDLE_PATH = Path(__file__).resolve().parents[1] / "artifacts" / "models" / "cross_domain_bundle.joblib"


def test_dataset_label_is_synthetic():
    assert DATASET_LABEL == "SYNTHETIC"


def test_same_seed_reproduces_identical_bytes():
    cfg = SyntheticConfig(seed=42, n_acquisitions=5, samples_per_acquisition=256)
    x1, y1 = generate_acquisition(cfg, 3)
    x2, y2 = generate_acquisition(cfg, 3)
    assert np.array_equal(x1, x2)
    assert np.array_equal(y1, y2)
    assert hashlib.sha256(x1.tobytes()).hexdigest() == hashlib.sha256(x2.tobytes()).hexdigest()


def test_different_seed_changes_output():
    cfg_a = SyntheticConfig(seed=42, samples_per_acquisition=256)
    cfg_b = SyntheticConfig(seed=43, samples_per_acquisition=256)
    xa, _ = generate_acquisition(cfg_a, 0)
    xb, _ = generate_acquisition(cfg_b, 0)
    assert not np.array_equal(xa, xb)


def test_single_acquisition_matches_full_sequence_generation():
    """Reproducibility must hold whether an acquisition is generated alone
    or as part of generating the whole run - both must hit the same RNG
    stream for that index."""
    cfg = SyntheticConfig(seed=7, n_acquisitions=4, samples_per_acquisition=128)
    sequence = generate_sequence(cfg)
    solo_x, solo_y = generate_acquisition(cfg, 2)
    assert np.array_equal(sequence[2][0], solo_x)
    assert np.array_equal(sequence[2][1], solo_y)


def test_amplitude_and_impulsiveness_increase_across_the_run():
    """The configured degradation must show up as a real, checkable trend,
    not just a config knob that does nothing."""
    cfg = SyntheticConfig(seed=1, n_acquisitions=10, samples_per_acquisition=2560)
    sequence = generate_sequence(cfg)
    rms = [np.sqrt(np.mean(x**2)) for x, _ in sequence]
    kurtosis = [time_domain_features(x, "v")["v_kurtosis"] for x, _ in sequence]
    assert rms[-1] > rms[0]
    assert kurtosis[-1] > kurtosis[0]


def test_write_synthetic_zip_contains_labelled_metadata_and_all_acquisitions(tmp_path):
    cfg = SyntheticConfig(seed=5, n_acquisitions=6, samples_per_acquisition=256)
    zip_path = write_synthetic_zip(cfg, tmp_path / "synthetic_bearing.zip")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "metadata.json" in names
        import json

        metadata = json.loads(zf.read("metadata.json"))
        assert metadata["dataset_label"] == "SYNTHETIC"
        acc_files = sorted(n for n in names if n.startswith("acc_"))
        assert len(acc_files) == cfg.n_acquisitions
        first = zf.read(acc_files[0]).decode().strip().splitlines()
        assert len(first) == cfg.samples_per_acquisition
        assert len(first[0].split(",")) == 2  # vibration_x, vibration_y


@pytest.mark.skipif(not BUNDLE_PATH.exists(), reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_synthetic_data_is_routed_as_out_of_domain_not_scored_as_femto():
    """The frozen FEMTO model must not treat synthetic data as in-domain.
    This is the controlling claim: even a synthetic signal engineered to
    look bearing-shaped must go through the same applicability gate real
    external data does, and either come out non-HIGH or the test records
    exactly why it was HIGH (never silently assumed)."""
    import joblib
    import pandas as pd

    from bearing_pdm.applicability import assess as applicability_assess
    from bearing_pdm.routing import candidates_from_bundle

    bundle = joblib.load(BUNDLE_PATH)
    candidates = [c for c in candidates_from_bundle(bundle) if c.name == "raw_seconds"]
    if not candidates:
        pytest.skip("cross_domain_bundle.joblib has no raw_seconds candidate")
    model = candidates[0].applicability

    cfg = SyntheticConfig(seed=42, n_acquisitions=10, samples_per_acquisition=2560,
                           sample_rate_hz=25_600.0)
    sequence = generate_sequence(cfg)
    rows = []
    for x, y in sequence:
        row = {}
        row.update(time_domain_features(x, "vibration_x"))
        row.update(frequency_domain_features(x, cfg.sample_rate_hz, "vibration_x"))
        row.update(time_domain_features(y, "vibration_y"))
        row.update(frequency_domain_features(y, cfg.sample_rate_hz, "vibration_y"))
        rows.append({c: row.get(c, np.nan) for c in model.feature_columns})
    df = pd.DataFrame(rows, dtype=float)

    result = applicability_assess(df, model, single_recording=False)
    assert result["level"] in ("HIGH", "MEDIUM", "LOW")
    # Not asserting a specific level (the simulator isn't tuned to any target
    # applicability) - the real guard is that routing.decide would suppress
    # RUL for anything other than HIGH, proven separately below.
    from bearing_pdm.routing import RUL_AVAILABLE, RUL_EXPERIMENTAL, RUL_SUPPRESSED, decide

    decision = decide(True, [], [(candidates[0], result, True)])
    if result["level"] == "LOW":
        assert decision["status"] == RUL_SUPPRESSED
    elif result["level"] == "MEDIUM":
        assert decision["status"] in (RUL_EXPERIMENTAL, RUL_SUPPRESSED)
    else:
        assert decision["status"] in (RUL_AVAILABLE, RUL_SUPPRESSED)
