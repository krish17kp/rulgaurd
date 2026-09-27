"""Tests for the read-only prediction API (src/bearing_pdm/api.py).

Uses the real cached artifacts under artifacts/models/ (small joblib files
committed to the repo), same as the dashboard tests - no network, no full
dataset needed.
"""

from __future__ import annotations

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


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_predict_rul_falls_back_to_median_for_missing_features():
    model = api._load_joblib("rul_extra_trees.joblib")
    partial = dict(list(model.median_fill.items())[:5])
    response = client.post(
        "/predict/rul", json={"dataset_id": "femto", "features": partial}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["features_missing"]) == len(model.feature_columns) - 5
