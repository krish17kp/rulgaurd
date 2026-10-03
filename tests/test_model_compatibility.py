"""POST /models/compatibility: metadata-only gate against the selected cached RUL
model (docs/dataset-compatibility.md, "Model compatibility")."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api, artifacts
from bearing_pdm.adapters import ADAPTERS

client = TestClient(api.app, raise_server_exceptions=False)

FEATURES = [
    "vibration_x_rms", "vibration_x_kurtosis", "vibration_x_dominant_frequency_hz",
    "vibration_y_rms", "vibration_y_kurtosis", "vibration_y_dominant_frequency_hz",
]
REAL_MODEL_PRESENT = (
    (api.MODELS_DIR / "rul_extra_trees.joblib").exists()
    and (api.MODELS_DIR / "rul_selected_model.json").exists()
)


@pytest.fixture
def fake_model(tmp_path, monkeypatch):
    """Selected-model metadata with a known schema, independent of the mounted artifacts."""
    (tmp_path / "rul_selected_model.json").write_text(json.dumps({"selected": "extra_trees"}))
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(api, "_MODEL_CACHE", {
        "rul_extra_trees.joblib": SimpleNamespace(feature_columns=tuple(FEATURES)),
    })


def check(dataset_id, feature_names, **extra):
    response = client.post("/models/compatibility", json={
        "dataset_id": dataset_id, "feature_names": feature_names, **extra,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["prediction_produced"] is False
    assert not {"rul_seconds", "rul_hours", "health_indicator"} & set(body)
    return body


def test_matching_femto_schema_is_fully_supported(fake_model):
    body = check("femto", FEATURES)
    assert body["compatibility"] == "FULLY_SUPPORTED"
    assert body["required_action"] == {"kind": "NONE", "message": body["required_action"]["message"],
                                       "missing": []}
    assert body["feature_schema"]["missing"] == [] and body["feature_schema"]["extra"] == []
    assert body["model"]["trained_dataset_id"] == "femto"
    assert body["model"]["name"] == "extra_trees"
    assert body["required_signals"] == ["vibration_x", "vibration_y"]
    assert body["sampling"] == {"rate_hz": 25_600.0, "source": "adapter_metadata", "compatible": True}
    assert "metadata check only" in body["required_action"]["message"]


def test_matching_femto_schema_with_matching_rate(fake_model):
    body = check("femto", list(reversed(FEATURES)), sampling_rate_hz=25_600)
    assert body["compatibility"] == "FULLY_SUPPORTED"
    assert body["sampling"] == {"rate_hz": 25_600.0, "source": "user", "compatible": True}


def test_femto_with_missing_features_needs_adapter_and_names_them(fake_model):
    body = check("femto", FEATURES[:-2])
    assert body["compatibility"] == "ADAPTER_REQUIRED"
    assert body["feature_schema"]["missing"] == FEATURES[-2:]
    assert body["required_action"]["kind"] == "ADAPTER_REQUIRED"
    assert "feature: vibration_y_dominant_frequency_hz" in body["required_action"]["missing"]


def test_femto_with_entirely_different_schema_needs_adapter(fake_model):
    body = check("femto", ["rms", "kurtosis"])
    assert body["compatibility"] == "ADAPTER_REQUIRED"
    assert body["feature_schema"]["missing"] == FEATURES
    assert body["feature_schema"]["extra"] == ["rms", "kurtosis"]


def test_femto_with_extra_features_is_supported_and_reports_them(fake_model):
    body = check("femto", FEATURES + ["bearing_temp_mean"])
    assert body["compatibility"] == "FULLY_SUPPORTED"
    assert body["feature_schema"]["extra"] == ["bearing_temp_mean"]
    assert body["reasons"] and "not used by the model" in body["reasons"][0]


def test_femto_at_a_different_sampling_rate_requires_retraining(fake_model):
    body = check("femto", FEATURES, sampling_rate_hz=20_000)
    assert body["compatibility"] == "RETRAIN_REQUIRED"
    assert body["sampling"]["compatible"] is False
    assert body["required_action"]["kind"] == "RETRAIN_REQUIRED"


@pytest.mark.parametrize("dataset_id", ["college", "ims", "xjtu"])
def test_other_registered_datasets_require_retraining_even_with_femto_schema(fake_model, dataset_id):
    body = check(dataset_id, FEATURES)
    assert body["compatibility"] == "RETRAIN_REQUIRED"
    assert body["compatibility"] != "FULLY_SUPPORTED"
    assert "D11" in body["reasons"][0]
    assert body["adapter"]["dataset_id"] == dataset_id
    assert body["sampling"]["rate_hz"] == ADAPTERS[dataset_id].sampling_rate_hz
    assert body["required_action"]["kind"] == "RETRAIN_REQUIRED"


@pytest.mark.parametrize("dataset_id", ["cwru", "my_factory_pump", "femto2"])
def test_unknown_dataset_is_unsupported(fake_model, dataset_id):
    body = check(dataset_id, FEATURES, sampling_rate_hz=12_000)
    assert body["compatibility"] == "UNSUPPORTED"
    assert body["adapter"] is None
    assert body["required_action"]["kind"] == "UNSUPPORTED_DATASET"
    assert body["sampling"] == {"rate_hz": 12_000.0, "source": "user", "compatible": None}


def test_dataset_id_is_normalised(fake_model):
    assert check(" FEMTO ", FEATURES)["compatibility"] == "FULLY_SUPPORTED"


@pytest.mark.parametrize("dataset_id, names", [
    ("", FEATURES),
    ("femto", []),
    ("femto", FEATURES + [FEATURES[0]]),
    ("femto", FEATURES + ["  "]),
])
def test_invalid_requests_are_invalid_input(fake_model, dataset_id, names):
    body = check(dataset_id, names)
    assert body["compatibility"] == "INVALID_INPUT"
    assert body["required_action"]["kind"] == "FIX_REQUEST"


@pytest.mark.parametrize("payload", [
    {"dataset_id": "femto"},
    {"feature_names": FEATURES},
    {"dataset_id": "femto", "feature_names": FEATURES, "sampling_rate_hz": 0},
    {"dataset_id": "femto", "feature_names": FEATURES, "sampling_rate_hz": -1},
    {"dataset_id": "femto", "feature_names": "vibration_x_rms"},
])
def test_malformed_body_is_validation_error(fake_model, payload):
    response = client.post("/models/compatibility", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def assert_model_unavailable(response):
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "MODEL_UNAVAILABLE" and body["retryable"] is True
    assert "compatibility" not in body


def test_missing_model_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(api, "_MODEL_CACHE", {})
    for dataset_id in ("femto", "college", "unknown"):
        assert_model_unavailable(client.post("/models/compatibility", json={
            "dataset_id": dataset_id, "feature_names": FEATURES,
        }))


def test_selected_model_json_present_but_artifact_missing_fails_closed(tmp_path, monkeypatch):
    (tmp_path / "rul_selected_model.json").write_text(json.dumps({"selected": "extra_trees"}))
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(api, "_MODEL_CACHE", {})
    assert_model_unavailable(client.post("/models/compatibility", json={
        "dataset_id": "femto", "feature_names": FEATURES,
    }))


@pytest.mark.parametrize("selected", ['{"selected": "naive"}', "not json", "{}"])
def test_unusable_selection_metadata_fails_closed(tmp_path, monkeypatch, selected):
    (tmp_path / "rul_selected_model.json").write_text(selected)
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(api, "_MODEL_CACHE", {
        "rul_extra_trees.joblib": SimpleNamespace(feature_columns=tuple(FEATURES)),
    })
    assert_model_unavailable(client.post("/models/compatibility", json={
        "dataset_id": "femto", "feature_names": FEATURES,
    }))


def test_outcome_is_logged_without_feature_names(fake_model, caplog):
    with caplog.at_level("INFO", logger="bearing_pdm.api"):
        check("femto", FEATURES[:1])
    record = next(r for r in caplog.records if getattr(r, "stage", None) == "model_compatibility")
    assert record.compatibility == "ADAPTER_REQUIRED"
    assert FEATURES[1] not in record.getMessage()


@pytest.mark.skipif(not REAL_MODEL_PRESENT, reason="cached RUL model artifacts not present")
def test_real_selected_model_schema_is_fully_supported_for_femto_only():
    columns = client.get("/models/info").json()["extra_trees_feature_columns"]
    assert check("femto", columns)["compatibility"] == "FULLY_SUPPORTED"
    assert check("college", columns)["compatibility"] == "RETRAIN_REQUIRED"
    assert check("femto", columns[1:])["compatibility"] == "ADAPTER_REQUIRED"
