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

import numpy as np
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


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_raw_femto_csv_upload_produces_the_same_prediction_as_manual_extraction():
    """Proves the new POST /predict/rul/femto-acquisition wiring (raw CSV ->
    features.py -> model, inside the API process) against the already-trusted
    manual-extraction path above, not just that it returns *some* 200."""
    acc_path = FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv"
    expected = client.post(
        "/predict/rul", json={"dataset_id": "femto", "features": _extract_features(acc_path)}
    ).json()

    with acc_path.open("rb") as fh:
        response = client.post(
            "/predict/rul/femto-acquisition",
            files={"file": ("acc_00001.csv", fh, "text/csv")},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rul_seconds"] == pytest.approx(expected["rul_seconds"])
    assert body["features_missing"] == []


def test_raw_femto_csv_upload_rejects_wrong_column_count():
    bad_csv = "1,2,3\n" * 300
    response = client.post(
        "/predict/rul/femto-acquisition",
        files={"file": ("bad.csv", bad_csv.encode(), "text/csv")},
    )
    assert response.status_code == 422
    assert "columns" in response.json()["detail"]


def test_femto_signal_endpoint_returns_real_waveform_fft_and_matching_features():
    """The Signal & FFT / Features UI reads this endpoint. Assert the waveform
    is literally the uploaded column (not reconstructed), the FFT length
    matches rfft's N//2+1, and the returned features equal the exact values
    /predict/rul/femto-acquisition would extract from the same file."""
    acc_path = FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv"
    import pandas as pd

    raw = pd.read_csv(acc_path, header=None)
    expected_features = _extract_features(acc_path)

    with acc_path.open("rb") as fh:
        response = client.post(
            "/analyze/femto-signal", files={"file": ("acc_00001.csv", fh, "text/csv")},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sample_rate_hz"] == 25600.0
    assert body["samples"] == len(raw)
    assert body["vibration_x"]["waveform"] == pytest.approx(raw[4].tolist())
    assert body["vibration_y"]["waveform"] == pytest.approx(raw[5].tolist())
    assert len(body["vibration_x"]["fft_magnitude"]) == len(raw) // 2 + 1
    assert len(body["vibration_x"]["fft_frequency_hz"]) == len(body["vibration_x"]["fft_magnitude"])
    for key, value in expected_features.items():
        assert body["features"][key] == pytest.approx(value), key


def test_femto_signal_endpoint_rejects_wrong_column_count():
    bad_csv = "1,2,3\n" * 300
    response = client.post(
        "/analyze/femto-signal", files={"file": ("bad.csv", bad_csv.encode(), "text/csv")},
    )
    assert response.status_code == 422


def _non_constant_femto_csv(amplitude: float) -> bytes:
    """A FEMTO-shaped CSV with real (non-constant) variation at a given
    amplitude - a constant-value column is caught earlier by the degenerate
    reference-window style checks upstream of feature extraction, so an
    overflow regression test needs a signal that actually varies."""
    rng = np.random.default_rng(0)
    n = api.FEMTO_ACQUISITION_SAMPLES
    x = rng.normal(size=n) * amplitude
    y = rng.normal(size=n) * amplitude
    lines = [f"0,0,0,0,{xi},{yi}" for xi, yi in zip(x, y)]
    return ("\n".join(lines) + "\n").encode()


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_raw_femto_csv_upload_rejects_overflowing_values_with_422_not_500():
    """Regression: an amplitude extreme enough to leave every feature value
    finite but too large for the model's input dtype must still come back
    422, not a raw 500 - whether it's caught by the applicability check
    (now the first line of defense: this amplitude is wildly out of the
    training distribution) or, if that's unavailable, by
    _predict_rul_from_features's own predict()-time dtype catch."""
    response = client.post(
        "/predict/rul/femto-acquisition",
        files={"file": ("overflow.csv", _non_constant_femto_csv(1e40), "text/csv")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"].lower()
    assert "unusable for prediction" in detail or "rul suppressed" in detail


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_raw_femto_csv_upload_predict_time_overflow_catch_still_works_without_applicability(monkeypatch):
    """The predict()-time dtype-overflow catch (api.py's ValueError handler
    around model.model.predict) is a backstop for when applicability itself
    is unavailable (e.g. the cross-domain bundle artifact is missing) - this
    pins that it still fires correctly in that situation, independent of
    the applicability check that now runs first when the bundle is present."""
    monkeypatch.setattr(api, "_applicability_candidate", lambda dataset_id: None)
    response = client.post(
        "/predict/rul/femto-acquisition",
        files={"file": ("overflow.csv", _non_constant_femto_csv(1e40), "text/csv")},
    )
    assert response.status_code == 422
    assert "unusable for prediction" in response.json()["detail"]


def test_raw_femto_csv_upload_rejects_values_overflowing_feature_extraction_itself():
    """Regression: an amplitude extreme enough to overflow inside
    features.py's own statistics (std**4 on a Python float raises
    OverflowError) before any feature value exists to check - this
    previously reached sklearn/numpy unhandled (500). Does not need the
    trained model: extraction fails before _predict_rul_from_features runs."""
    response = client.post(
        "/predict/rul/femto-acquisition",
        files={"file": ("overflow.csv", _non_constant_femto_csv(1e80), "text/csv")},
    )
    assert response.status_code == 422
    assert "too extreme to extract" in response.json()["detail"]


def test_raw_femto_csv_upload_rejects_too_few_rows():
    bad_csv = "\n".join(["0,0,0,0,0.1,0.2"] * 5)
    response = client.post(
        "/predict/rul/femto-acquisition",
        files={"file": ("short.csv", bad_csv.encode(), "text/csv")},
    )
    assert response.status_code == 422
    assert "rows" in response.json()["detail"]


def _real_acquisition_lines() -> list[str]:
    return (FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv").read_text().splitlines()


@pytest.mark.parametrize("n_rows", [256, 2559, 2561, 5120])
def test_raw_femto_csv_upload_rejects_an_incomplete_or_concatenated_acquisition(n_rows, monkeypatch):
    """Regression (femto-acquisition-v1, the contract /analyze/rul enforces):
    the model's features were computed on complete 2560-sample acquisitions.
    A truncated file, or two concatenated, previously reached the model
    (anything >= 256 rows was accepted) with length-dependent features it was
    never trained on, gated only by whether applicability happened to flag it."""
    lines = _real_acquisition_lines()
    rows = (lines * 2)[:n_rows]
    monkeypatch.setattr(api, "_predict_rul_from_features",
                        lambda *_: pytest.fail("RUL must not run"))
    response = client.post(
        "/predict/rul/femto-acquisition",
        files={"file": ("acc.csv", ("\n".join(rows) + "\n").encode(), "text/csv")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INCOMPLETE_ACQUISITION"
    assert body["compatibility"] == "INVALID_INPUT"
    assert f"Got {n_rows} rows" in body["detail"]


def test_raw_femto_csv_upload_rejects_missing_samples(monkeypatch):
    lines = _real_acquisition_lines()
    fields = lines[100].split(",")
    lines[100] = ",".join(fields[:5] + [""])  # one blank vibration sample
    monkeypatch.setattr(api, "_predict_rul_from_features",
                        lambda *_: pytest.fail("RUL must not run"))
    response = client.post(
        "/predict/rul/femto-acquisition",
        files={"file": ("acc.csv", ("\n".join(lines) + "\n").encode(), "text/csv")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INCOMPLETE_ACQUISITION"
    assert "1 vibration sample(s) are missing" in response.json()["detail"]


def test_raw_femto_csv_upload_rejects_binary_and_records_no_filename(monkeypatch):
    from bearing_pdm.history import InMemoryHistoryStore

    store = InMemoryHistoryStore()
    monkeypatch.setattr(api, "_history_store", store)
    response = client.post(
        "/predict/rul/femto-acquisition",
        files={"file": ("acc.csv", b"PK\x03\x04binary", "text/csv")},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_FILE_TYPE"

    secret = "patient-7-SECRETNAME.csv"
    lines = _real_acquisition_lines()[:10]
    client.post("/predict/rul/femto-acquisition",
                files={"file": (secret, ("\n".join(lines) + "\n").encode(), "text/csv")})
    record = store.recent()[0]
    assert record["kind"] == "predict_rul_femto_acquisition"
    assert record["status"] == "failed" and record["error_code"] == "INCOMPLETE_ACQUISITION"
    assert record["request"] == {"dataset_id": "femto", "source": "upload", "n_rows": 10}
    assert "SECRETNAME" not in str(store.recent())


def test_two_real_acquisitions_from_the_same_bearing_give_different_features():
    """Sanity check that the fixtures are actually two distinct real
    recordings, not duplicates - otherwise the e2e test above would pass
    trivially against degenerate input."""
    f1 = _extract_features(FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv")
    f2 = _extract_features(FIXTURES / "femto" / "Bearing1_1" / "acc_00002.csv")
    assert f1 != f2
