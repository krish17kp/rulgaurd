"""Tests for the read-only prediction API (src/bearing_pdm/api.py).

Uses the real cached artifacts under artifacts/models/ when present (they are
gitignored, same as dashboard.py's artifacts - not committed). Tests that need
the model skip cleanly on a checkout without them; health/gating tests do not
depend on the artifact's presence.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api

MODEL_PRESENT = (api.MODELS_DIR / "rul_extra_trees.joblib").exists()

client = TestClient(api.app)


def test_health_reports_model_status():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["models_loaded"]["rul_extra_trees"] == MODEL_PRESENT


def test_models_info_lists_femto_only():
    response = client.get("/models/info")
    assert response.status_code == 200
    assert response.json()["supported_datasets"] == ["femto"]


def test_predict_rul_rejects_non_femto_dataset():
    response = client.post(
        "/predict/rul", json={"dataset_id": "college", "features": {}}
    )
    assert response.status_code == 422
    assert "femto" in response.json()["detail"].lower()


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_accepts_full_feature_row():
    model = api._load_joblib("rul_extra_trees.joblib")
    features = dict(model.median_fill)
    response = client.post(
        "/predict/rul", json={"dataset_id": "femto", "features": features}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "extra_trees"
    assert body["rul_hours"] == pytest.approx(body["rul_seconds"] / 3600.0)
    assert body["features_missing"] == []


FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def test_dataset_inspect_rejects_empty_file():
    response = client.post(
        "/dataset/inspect", files={"file": ("empty.csv", b"", "text/csv")}
    )
    assert response.status_code == 422


def test_dataset_inspect_requires_adapter_for_headerless_femto_fixture():
    path = FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv"
    with open(path, "rb") as f:
        response = client.post("/dataset/inspect", files={"file": (path.name, f, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "ADAPTER_REQUIRED"
    assert body["profile"]["has_header"] is False


def test_dataset_inspect_fully_supported_for_clean_header_csv():
    csv_bytes = b"vibration_x,vibration_y\n0.1,0.2\n0.3,0.4\n0.2,0.1\n"
    response = client.post(
        "/dataset/inspect", files={"file": ("clean.csv", csv_bytes, "text/csv")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "FULLY_SUPPORTED"
    assert body["reasons"] == []


def test_dataset_inspect_unsupported_for_no_recognisable_sensor_columns():
    csv_bytes = b"foo,bar\n1,2\n3,4\n"
    response = client.post(
        "/dataset/inspect", files={"file": ("unrelated.csv", csv_bytes, "text/csv")}
    )
    assert response.status_code == 200
    assert response.json()["compatibility"] == "UNSUPPORTED"


def test_dataset_inspect_rejects_oversized_upload(monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 10)
    response = client.post(
        "/dataset/inspect",
        files={"file": ("big.csv", b"vibration_x\n" + b"1.0\n" * 100, "text/csv")},
    )
    assert response.status_code == 413


def test_vercel_app_mounts_routes_under_api_prefix():
    vercel_client = TestClient(api.vercel_app)
    response = vercel_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_predict_rul_returns_503_when_model_artifact_missing(monkeypatch):
    monkeypatch.setattr(api, "MODELS_DIR", api.MODELS_DIR.parent / "does-not-exist")
    api._MODEL_CACHE.clear()
    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": {}})
    assert response.status_code == 503
    api._MODEL_CACHE.clear()


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_rejects_mostly_missing_features():
    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": {}})
    assert response.status_code == 422
    assert "missing" in response.json()["detail"].lower()


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_falls_back_to_median_for_missing_features():
    model = api._load_joblib("rul_extra_trees.joblib")
    n_provided = len(model.feature_columns) - 2  # under the max_missing_fraction gate
    partial = dict(list(model.median_fill.items())[:n_provided])
    response = client.post(
        "/predict/rul", json={"dataset_id": "femto", "features": partial}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["features_missing"]) == len(model.feature_columns) - n_provided
