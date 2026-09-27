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


def test_requests_get_a_request_id_header_and_are_logged(caplog):
    with caplog.at_level("INFO", logger="bearing_pdm.api"):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert any("path=/health" in r.message and "status=200" in r.message for r in caplog.records)


def test_health_reports_model_status():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["models_loaded"]["rul_extra_trees"] == MODEL_PRESENT


EVALUATION_PRESENT = (api.METRICS_DIR / "rul_evaluation.json").exists()


@pytest.mark.skipif(not EVALUATION_PRESENT, reason="reports/metrics/rul_evaluation.json not present")
def test_models_evaluation_returns_real_metrics_with_college_caveat():
    response = client.get("/models/evaluation")
    assert response.status_code == 200
    body = response.json()
    assert "femto_lobo_mean_mae_by_model" in body
    assert "extra_trees" in body["femto_lobo_mean_mae_by_model"]
    # D10: college naive's MAE=0.0 must never travel without its caveat.
    assert "college_naive_caveat" in body
    assert "oracle" in body["college_naive_caveat"].lower()


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


def test_dataset_inspect_invalid_for_non_numeric_vibration_column():
    csv_bytes = b"vibration_x\nabc\ndef\n"
    response = client.post("/dataset/inspect", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    assert response.json()["compatibility"] == "INVALID_INPUT"


def test_dataset_inspect_invalid_for_all_missing_vibration_column():
    csv_bytes = b"vibration_x,vibration_y\n,0.1\n,0.2\n,0.3\n"
    response = client.post("/dataset/inspect", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    # vibration_x is 100% missing but vibration_y is fully usable - still supported.
    assert response.json()["compatibility"] == "FULLY_SUPPORTED"


def test_dataset_inspect_invalid_when_every_vibration_column_is_missing():
    csv_bytes = b"vibration_x\n\n\n\n"
    response = client.post("/dataset/inspect", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    assert response.json()["compatibility"] == "INVALID_INPUT"


def test_dataset_inspect_invalid_for_constant_vibration_column():
    csv_bytes = b"vibration_x\n1.0\n1.0\n1.0\n"
    response = client.post("/dataset/inspect", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    assert response.json()["compatibility"] == "INVALID_INPUT"


def test_dataset_inspect_invalid_for_all_infinite_vibration_column():
    csv_bytes = b"vibration_x\ninf\ninf\n-inf\ninf\n"
    response = client.post("/dataset/inspect", files={"file": ("bad.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert body["compatibility"] == "INVALID_INPUT"
    assert "infinite" in " ".join(body["reasons"]).lower()


def test_dataset_inspect_invalid_for_header_only_file():
    csv_bytes = b"vibration_x,vibration_y\n"
    response = client.post("/dataset/inspect", files={"file": ("empty_rows.csv", csv_bytes, "text/csv")})
    assert response.status_code == 200
    assert response.json()["compatibility"] == "INVALID_INPUT"


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


def test_oversized_content_length_is_rejected_before_body_is_read():
    huge = api._MAX_REQUEST_BYTES + 1
    response = client.post(
        "/predict/hi",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": str(huge)},
    )
    assert response.status_code == 413


def test_vercel_app_mounts_routes_under_api_prefix():
    vercel_client = TestClient(api.vercel_app)
    response = vercel_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


HI_MODEL_PRESENT = (api.MODELS_DIR / "reference_hi_model.joblib").exists()


def test_predict_hi_rejects_non_femto_dataset():
    response = client.post("/predict/hi", json={"dataset_id": "college", "rows": [{"sequence_index": 0}]})
    assert response.status_code == 422


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_rows_missing_feature_columns():
    response = client.post(
        "/predict/hi", json={"dataset_id": "femto", "rows": [{"sequence_index": 0}]}
    )
    assert response.status_code == 422


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_a_run_shorter_than_the_reference_window():
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    too_few = min_rows - 1
    rows = [
        {"sequence_index": i, **{f: 1000.0 for f in hi_model.features}}
        for i in range(too_few)
    ]
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 422
    assert "reference window" in response.json()["detail"].lower()


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_constant_reference_window_even_when_long_enough():
    """The exact case review found fail-open: enough rows to pass the
    min-length gate, but every row identical, so the model can't tell
    'healthy' from 'stuck sensor' - was silently scored 100% HEALTHY."""
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = [
        {"sequence_index": i, **{f: 1000.0 for f in hi_model.features}}
        for i in range(min_rows)
    ]
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 422
    assert "variation" in response.json()["detail"].lower()


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_reference_window_with_only_float_jitter():
    """Regression for the exact gap review found in the previous fix: exact
    nunique()<=1 was defeated by a ~1e-7 perturbation, which is far below
    the model's fitted per-feature scale and should still count as
    'no real variation.'"""
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = [
        {"sequence_index": i, **{f: 1000.0 + (i % 2) * 1e-7 for f in hi_model.features}}
        for i in range(min_rows)
    ]
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 422
    assert "variation" in response.json()["detail"].lower()


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_reference_window_with_only_one_varying_feature():
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = []
    for i in range(min_rows):
        row = {"sequence_index": i}
        for j, f in enumerate(hi_model.features):
            row[f] = 1000.0 + (i * 10.0 if j == 0 else 0.0)  # only the first feature moves
        rows.append(row)
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 422


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_rejects_non_finite_feature_values():
    hi_model = api._load_joblib("reference_hi_model.joblib")
    min_rows = hi_model.reference_skip + hi_model.reference_n
    rows = [
        {"sequence_index": i, **{f: 1.0 + i * 0.01 for f in hi_model.features}}
        for i in range(min_rows)
    ]
    rows[-1][hi_model.features[0]] = float("inf")
    # Python's json.dumps allows Infinity by default (non-standard but valid
    # for this test's purpose: exercising what api.py does once a value is a
    # float('inf')) - build the body manually since httpx's own client-side
    # encoder is stricter than that.
    import json as json_module

    body = json_module.dumps({"dataset_id": "femto", "rows": rows})
    response = client.post(
        "/predict/hi", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "non-finite" in response.json()["detail"].lower()


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_predict_hi_returns_declining_health_indicator():
    hi_model = api._load_joblib("reference_hi_model.joblib")
    n = 60
    rows = []
    for i in range(n):
        row = {"sequence_index": i}
        for feature in hi_model.features:
            # reference_skip=10, reference_n=50 -> reference window is rows
            # [10, 60). Rows 50-59 fall inside that window AND get the jump,
            # so the window itself has real variation (passes the
            # degenerate-window check) while still producing a clear
            # late-run degradation signature, not noise.
            row[feature] = 1.0 if i < 50 else 5.0
        rows.append(row)
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == n
    assert all(0.0 < r["health_indicator"] < 1.0 for r in body["rows"])
    # Later (degraded) rows must score lower than the healthy reference rows.
    early_hi = body["rows"][10]["health_indicator"]
    late_hi = body["rows"][-1]["health_indicator"]
    assert late_hi < early_hi
    assert {r["stage"] for r in body["rows"]} <= {"HEALTHY", "DEGRADING", "CRITICAL"}


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
