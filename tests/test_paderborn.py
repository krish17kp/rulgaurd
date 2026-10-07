"""Paderborn KAt-DataCenter adapter tests, against real (excerpted)
downloaded signal bytes - see docs/external-datasets.md for provenance.
Paderborn recordings are fixed-condition snapshots, not run-to-failure:
these tests must never assert an RUL value for it."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from bearing_pdm.applicability import assess as applicability_assess
from bearing_pdm.paderborn import (
    DATASET_TYPE,
    VIBRATION_SAMPLE_RATE_HZ,
    extract_features,
    parse_filename,
    read_channel,
)
from bearing_pdm.routing import candidates_from_bundle

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "paderborn"
BUNDLE_PATH = Path(__file__).resolve().parents[1] / "artifacts" / "models" / "cross_domain_bundle.joblib"

PADERBORN_FIXTURES = {
    "N15_M07_F10_K001_1": "healthy (K001)",
    "N15_M07_F10_KA01_1": "artificial outer-race fault (KA01)",
}


def test_dataset_type_is_fault_diagnosis_not_run_to_failure():
    assert DATASET_TYPE == "FAULT_DIAGNOSIS"


def test_parse_filename_extracts_operating_condition_and_code():
    info = parse_filename(FIXTURES / "N15_M07_F10_KA01_1.mat")
    assert info == {"speed_code": "15", "torque_code": "07", "force_code": "10",
                     "bearing_code": "KA01", "run": "1"}


def test_parse_filename_rejects_non_conforming_name():
    with pytest.raises(ValueError):
        parse_filename(Path("not_a_paderborn_file.mat"))


@pytest.mark.parametrize("file_id", PADERBORN_FIXTURES)
def test_read_channel_returns_real_signal(file_id):
    signal = read_channel(FIXTURES / f"{file_id}.mat")
    assert signal.ndim == 1
    assert signal.size == 25_600  # 0.4s excerpt at 64kHz, see fixture generation
    assert signal.dtype == np.float64
    assert np.isfinite(signal).all()
    assert signal.std() > 0


def test_fault_has_higher_rms_than_healthy():
    """Real, checkable discriminator - not a fabricated claim."""
    healthy = read_channel(FIXTURES / "N15_M07_F10_K001_1.mat")
    fault = read_channel(FIXTURES / "N15_M07_F10_KA01_1.mat")
    assert np.sqrt(np.mean(fault**2)) > np.sqrt(np.mean(healthy**2))


@pytest.mark.parametrize("file_id", PADERBORN_FIXTURES)
def test_extract_features_produces_vibration_x_only(file_id):
    features = extract_features(FIXTURES / f"{file_id}.mat")
    assert "vibration_x_rms" in features
    assert "vibration_x_dominant_frequency_hz" in features
    assert all(k.startswith("vibration_x_") for k in features)
    assert all(np.isfinite(v) for v in features.values())


@pytest.mark.skipif(not BUNDLE_PATH.exists(), reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_paderborn_applicability_against_frozen_femto_model():
    """Real OOD check, same pattern as test_cwru.py: Paderborn fed through
    the exact applicability.assess() the live API uses, scoring against the
    real fitted ApplicabilityModel. Never asserts a specific level in
    advance - just that the pipeline runs and correctly reports the missing
    vibration_y_* columns (Paderborn, like CWRU, has only one accelerometer
    channel per recording)."""
    import joblib
    import pandas as pd

    bundle = joblib.load(BUNDLE_PATH)
    candidates = [c for c in candidates_from_bundle(bundle) if c.name == "raw_seconds"]
    if not candidates:
        pytest.skip("cross_domain_bundle.joblib has no raw_seconds candidate")
    model = candidates[0].applicability

    rows = []
    for file_id in PADERBORN_FIXTURES:
        features = extract_features(FIXTURES / f"{file_id}.mat", sample_rate_hz=VIBRATION_SAMPLE_RATE_HZ)
        rows.append({c: features.get(c, np.nan) for c in model.feature_columns})
    df = pd.DataFrame(rows, dtype=float)

    result = applicability_assess(df, model, single_recording=False)
    assert result["level"] in ("HIGH", "MEDIUM", "LOW")
    missing_y = [c for c in result["missing_features"] if c.startswith("vibration_y_")]
    assert missing_y, "vibration_y_* columns should be reported missing for a single-axis dataset"
