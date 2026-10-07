"""CWRU adapter tests, against real (excerpted) downloaded signal bytes -
see docs/external-datasets.md for provenance. CWRU is fault-diagnosis data,
not run-to-failure: these tests must never assert an RUL value for it."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from bearing_pdm.applicability import assess as applicability_assess
from bearing_pdm.cwru import (
    DATASET_TYPE,
    available_channels,
    extract_features,
    read_channel,
    read_rpm,
)
from bearing_pdm.routing import candidates_from_bundle

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "cwru"
BUNDLE_PATH = Path(__file__).resolve().parents[1] / "artifacts" / "models" / "cross_domain_bundle.joblib"

# file_id -> (fault label, as documented at engineering.case.edu/bearingdatacenter)
CWRU_FIXTURES = {
    "97": "normal baseline",
    "105": "inner race fault 0.007in",
    "118": "ball fault 0.007in",
    "130": "outer race fault 0.007in @6:00",
}


def test_dataset_type_is_fault_diagnosis_not_run_to_failure():
    """The controlling claim this adapter must never violate."""
    assert DATASET_TYPE == "FAULT_DIAGNOSIS"


@pytest.mark.parametrize("file_id", CWRU_FIXTURES)
def test_read_channel_returns_real_signal(file_id):
    path = FIXTURES / f"{file_id}.mat"
    signal = read_channel(path, file_id, channel="DE")
    assert signal.ndim == 1
    assert signal.size == 12_000  # 1s excerpt at 12kHz, see fixture generation
    assert signal.dtype == np.float64
    assert np.isfinite(signal).all()
    assert signal.std() > 0  # not a constant/corrupted read


@pytest.mark.parametrize("file_id", CWRU_FIXTURES)
def test_available_channels_reports_de(file_id):
    path = FIXTURES / f"{file_id}.mat"
    assert "DE" in available_channels(path)


def test_normal_baseline_has_lower_rms_than_outer_race_fault():
    """A real, checkable discriminator between fault conditions - not a
    fabricated claim. Outer-race faults are the most severe of this set at
    this fault diameter in the published literature."""
    normal = read_channel(FIXTURES / "97.mat", "97")
    outer_race = read_channel(FIXTURES / "130.mat", "130")
    assert np.sqrt(np.mean(outer_race**2)) > np.sqrt(np.mean(normal**2))


@pytest.mark.parametrize("file_id", CWRU_FIXTURES)
def test_extract_features_produces_vibration_x_only(file_id):
    path = FIXTURES / f"{file_id}.mat"
    features = extract_features(path, file_id, sample_rate_hz=12_000.0)
    assert "vibration_x_rms" in features
    assert "vibration_x_dominant_frequency_hz" in features
    assert all(k.startswith("vibration_x_") for k in features)
    assert all(np.isfinite(v) for v in features.values())


@pytest.mark.skipif(not BUNDLE_PATH.exists(), reason="artifacts/models/cross_domain_bundle.joblib not present")
def test_cwru_applicability_against_frozen_femto_model():
    """Real OOD check: CWRU fed through the exact applicability.assess() the
    live API uses for FEMTO uploads, scoring against the real fitted
    ApplicabilityModel - never asserting LOW/HIGH in advance, just that the
    real pipeline produces *some* level and never crashes on CWRU's missing
    vibration_y columns (ml-data.md: a dataset_type the model was never fit
    on must be routed through applicability, not silently scored as if
    in-domain)."""
    import joblib

    bundle = joblib.load(BUNDLE_PATH)
    candidates = [c for c in candidates_from_bundle(bundle) if c.name == "raw_seconds"]
    if not candidates:
        pytest.skip("cross_domain_bundle.joblib has no raw_seconds candidate")
    model = candidates[0].applicability

    import pandas as pd

    rows = []
    for file_id in CWRU_FIXTURES:
        features = extract_features(FIXTURES / f"{file_id}.mat", file_id, sample_rate_hz=12_000.0)
        rows.append({c: features.get(c, np.nan) for c in model.feature_columns})
    df = pd.DataFrame(rows, dtype=float)

    result = applicability_assess(df, model, single_recording=False)
    assert result["level"] in ("HIGH", "MEDIUM", "LOW")
    # CWRU has no vibration_y_* channel at all - every such column must be
    # reported missing, never silently treated as zero/in-domain.
    missing_y = [c for c in result["missing_features"] if c.startswith("vibration_y_")]
    assert missing_y, "vibration_y_* columns should be reported missing for a single-axis dataset"


def test_rpm_absent_for_97_or_present_and_finite():
    """97.mat (normal baseline) was recorded without an RPM variable in the
    original archive for some file ids; read_rpm must say so honestly
    (None) rather than raising or guessing a value."""
    rpm = read_rpm(FIXTURES / "97.mat", "97")
    assert rpm is None or (np.isfinite(rpm) and rpm > 0)
