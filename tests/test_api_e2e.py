"""End-to-end test: real FEMTO fixture bytes -> the actual feature-extraction
functions (features.py) -> the live API (api.py) -> a real RUL prediction.

goals.md asks to "test the full prediction flow end-to-end using existing
project datasets." Every other test in tests/test_api.py posts synthetic or
median-derived feature dicts; this is the one place that proves the API's
feature-column contract actually matches what the real extraction pipeline
produces for real acquisition data, not just what the API's own tests assume
it produces.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api
from bearing_pdm.features import frequency_domain_features, time_domain_features
from bearing_pdm.femto import ACC_COLUMNS

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"
FEMTO_SAMPLE_RATE_HZ = 25600.0

client = TestClient(api.app)
MODEL_PRESENT = (api.MODELS_DIR / "rul_extra_trees.joblib").exists()


def _extract_features(acc_path: Path) -> dict[str, float]:
    """Mirrors what pipeline.py does for one FEMTO acquisition: time- and
    frequency-domain features per axis, using the real extraction functions
    from features.py (not reimplemented here)."""
    df = pd.read_csv(acc_path, header=None, names=ACC_COLUMNS, dtype="float64")
    features: dict[str, float] = {}
    for axis, column in (("x", "accel_horizontal"), ("y", "accel_vertical")):
        signal = df[column].to_numpy()
        features.update(time_domain_features(signal, f"vibration_{axis}"))
    for axis, column in (("x", "accel_horizontal"), ("y", "accel_vertical")):
        signal = df[column].to_numpy()
        features.update(frequency_domain_features(signal, FEMTO_SAMPLE_RATE_HZ, f"vibration_{axis}"))
    return features


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_real_femto_acquisition_produces_a_prediction_through_the_live_api():
    acc_path = FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv"
    features = _extract_features(acc_path)

    model = api._load_joblib("rul_extra_trees.joblib")
    # The extraction above must produce every column the trained model
    # expects - this is the actual contract check, not an assumption.
    missing = [c for c in model.feature_columns if c not in features]
    assert missing == [], f"real feature extraction is missing model columns: {missing}"

    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": features})
    assert response.status_code == 200
    body = response.json()
    assert body["features_missing"] == []
    # A loose sanity bound, not a precision check (this is a learning bearing
    # the model trained on, so the number can't be cited as held-out evidence
    # - see docs/decisions.md and ml-data.md). It rules out the failure mode
    # the "missing == []" check alone can't: silently-wrong feature math that
    # still produces *a* finite number, e.g. hours-scale FEMTO life coming
    # back as seconds or as some absurd multi-year value.
    assert 0 <= body["rul_seconds"] <= 7 * 24 * 3600  # FEMTO learning runs are minutes-to-hours, not days
    assert body["rul_hours"] == pytest.approx(body["rul_seconds"] / 3600.0)


def test_two_real_acquisitions_from_the_same_bearing_give_different_features():
    """Sanity check that the fixtures are actually two distinct real
    recordings, not duplicates - otherwise the e2e test above would pass
    trivially against degenerate input."""
    f1 = _extract_features(FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv")
    f2 = _extract_features(FIXTURES / "femto" / "Bearing1_1" / "acc_00002.csv")
    assert f1 != f2
