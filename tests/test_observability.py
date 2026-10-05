"""Structured request observability (docs/observability.md): every request emits
one access record carrying the documented fields, failures carry the stable
error `code`, and no feature value, sensor value, filename, exception text or
filesystem path ever reaches the logs."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api, artifacts

client = TestClient(api.app, raise_server_exceptions=False)

MODEL_PRESENT = (api.MODELS_DIR / "rul_extra_trees.joblib").exists()
HI_MODEL_PRESENT = (api.MODELS_DIR / "reference_hi_model.joblib").exists()

SECRET_FILENAME = "patient-7-pump-SECRETNAME.csv"
SECRET_VALUE = "987.654321"
SECRET_FEATURE = 0.123456789


def access_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "bearing_pdm.api" and hasattr(r, "request_id")]


def only_record(caplog) -> logging.LogRecord:
    records = access_records(caplog)
    assert len(records) == 1, [r.getMessage() for r in caplog.records]
    return records[0]


def assert_absent(caplog, *forbidden: str) -> None:
    haystack = caplog.text + " ".join(str(vars(r)) for r in caplog.records)
    for text in forbidden:
        assert text not in haystack, text


def multipart_file(name: str, data: bytes):
    return {"file": (name, data, "text/csv")}


def test_access_record_has_the_documented_fields(caplog):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.get("/health")
    record = only_record(caplog)
    assert record.request_id == response.headers["X-Request-ID"]
    assert (record.method, record.path, record.status) == ("GET", "/health", 200)
    assert record.stage == "health"
    assert isinstance(record.duration_ms, float) and record.duration_ms >= 0
    assert not hasattr(record, "code")
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert f"request_id={record.request_id}" in message
    assert "stage=health" in message and "status=200" in message and "duration_ms=" in message


def test_request_ids_are_distinct_per_request(caplog):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        client.get("/health")
        client.get("/health")
    first, second = access_records(caplog)
    assert first.request_id != second.request_id


@pytest.mark.parametrize(
    ("method", "path", "stage"),
    [
        ("get", "/models/info", "model_info"),
        ("get", "/models/evaluation", "model_evaluation"),
        ("get", "/predictions/history", "prediction_history"),
        ("post", "/predict/rul", "predict_rul"),
        ("post", "/predict/hi", "predict_hi"),
        ("post", "/dataset/inspect", "dataset_inspect"),
        ("get", "/no/such/route", "unmatched"),
    ],
)
def test_stage_is_the_endpoint(caplog, method, path, stage):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        getattr(client, method)(path)
    assert only_record(caplog).stage == stage


def test_vercel_mount_prefix_maps_to_the_same_stage():
    assert api._stage_for("/api/predict/rul") == "predict_rul"
    assert api._stage_for("/predict/rul") == "predict_rul"
    assert api._stage_for("/api/nope") == "unmatched"


def test_control_characters_in_the_path_cannot_forge_log_lines(caplog):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        client.get("/x%0Arequest_id=forged%0Dstatus=200")
    record = only_record(caplog)
    assert "\n" not in record.getMessage() and "\r" not in record.getMessage()
    assert record.stage == "unmatched"
    assert record.status == 404 and record.code == "NOT_FOUND"


def test_failure_records_carry_the_stable_error_code(caplog):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.post(
            "/predict/rul",
            json={"dataset_id": "college", "features": {"vibration_x_rms": SECRET_FEATURE}},
        )
    assert response.json()["code"] == "UNSUPPORTED_DATASET"
    record = only_record(caplog)
    assert record.code == "UNSUPPORTED_DATASET"
    assert record.status == 422 and record.stage == "predict_rul"
    assert "code=UNSUPPORTED_DATASET" in record.getMessage()
    assert not hasattr(record, "model_name")
    assert_absent(caplog, str(SECRET_FEATURE), "vibration_x_rms")


def test_validation_error_is_coded_without_echoing_the_body(caplog):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        client.post("/predict/rul", json={"features": {"vibration_x_rms": SECRET_FEATURE}})
    record = only_record(caplog)
    assert record.code == "VALIDATION_ERROR" and record.status == 422
    assert_absent(caplog, str(SECRET_FEATURE), "vibration_x_rms")


def test_model_unavailable_is_a_warning_with_code_and_no_model_fields(monkeypatch, caplog):
    monkeypatch.setattr(api, "_load_joblib", lambda name: None)
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.post(
            "/predict/rul", json={"dataset_id": "femto", "features": {"a": SECRET_FEATURE}}
        )
    assert response.status_code == 503
    record = only_record(caplog)
    assert record.code == "MODEL_UNAVAILABLE" and record.status == 503
    assert record.levelno == logging.WARNING
    assert not hasattr(record, "model_version")
    assert_absent(caplog, str(SECRET_FEATURE))


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_successful_rul_prediction_logs_model_and_schema_version_not_features(caplog):
    model = api._load_joblib("rul_extra_trees.joblib")
    features = dict(model.median_fill)
    features[model.feature_columns[0]] = SECRET_FEATURE
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.post("/predict/rul", json={"dataset_id": "femto", "features": features})
    assert response.status_code == 200
    record = only_record(caplog)
    assert record.stage == "predict_rul" and record.status == 200
    assert record.model_name == "extra_trees"
    assert record.model_version.startswith("sha256:")
    assert record.feature_schema_version.startswith("sha256:")
    assert not hasattr(record, "code")
    version, schema = api._model_provenance("predict_rul", "rul_extra_trees.joblib")
    assert (record.model_version, record.feature_schema_version) == (version, schema)
    forbidden = [str(SECRET_FEATURE), str(response.json()["rul_seconds"])]
    forbidden += [repr(v) for v in features.values() if len(repr(v)) >= 10]
    assert_absent(caplog, *forbidden)


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_failure_after_model_load_still_reports_the_model(caplog):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.post("/predict/rul", json={"dataset_id": "femto", "features": {}})
    assert response.json()["code"] == "FEATURES_MISSING"
    record = only_record(caplog)
    assert record.code == "FEATURES_MISSING"
    assert record.model_name == "extra_trees" and record.model_version.startswith("sha256:")


@pytest.mark.skipif(not HI_MODEL_PRESENT, reason="artifacts/models/reference_hi_model.joblib not present")
def test_hi_request_logs_model_fields_and_code_not_rows(caplog):
    rows = [{"sequence_index": 0, "vibration_x_rms": SECRET_FEATURE}]
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.json()["code"] == "FEATURES_MISSING"
    record = only_record(caplog)
    assert record.stage == "predict_hi" and record.model_name == "reference_hi"
    assert record.model_version.startswith("sha256:")
    assert record.feature_schema_version.startswith("sha256:")
    assert_absent(caplog, str(SECRET_FEATURE))


def test_inspect_logs_compatibility_but_not_filename_or_values(caplog):
    data = f"vibration_x,vibration_y\n{SECRET_VALUE},1.5\n2.25,{SECRET_VALUE}\n3.5,4.75\n".encode()
    with caplog.at_level(logging.DEBUG, logger="bearing_pdm.api"):
        response = client.post(
            "/dataset/inspect", files=multipart_file(SECRET_FILENAME, data),
            data={"declared_sampling_rate_hz": "25600", "declared_units": "g"},
        )
    assert response.status_code == 200, response.text
    record = only_record(caplog)
    assert record.stage == "dataset_inspect" and record.status == 200
    assert record.compatibility == response.json()["compatibility"] == "FULLY_SUPPORTED"
    assert "compatibility=FULLY_SUPPORTED" in record.getMessage()
    assert not hasattr(record, "code")
    assert_absent(caplog, SECRET_FILENAME, "SECRETNAME", SECRET_VALUE, "25600", "vibration_x")


@pytest.mark.parametrize(
    ("data", "compatibility"),
    [
        (b"a,b\n1,2\n3,4\n", "UNSUPPORTED"),
        (b"\n", "INVALID_INPUT"),
    ],
)
def test_inspect_logs_non_supported_outcomes(caplog, data, compatibility):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.post("/dataset/inspect", files=multipart_file(SECRET_FILENAME, data))
    assert response.status_code == 200
    record = only_record(caplog)
    assert record.compatibility == compatibility
    assert_absent(caplog, SECRET_FILENAME)


def test_inspect_rejection_logs_code_without_filename(caplog):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.post(
            "/dataset/inspect", files=multipart_file(SECRET_FILENAME, b"PK\x03\x04binary")
        )
    assert response.json()["code"] == "UNSUPPORTED_FILE_TYPE"
    record = only_record(caplog)
    assert record.code == "UNSUPPORTED_FILE_TYPE" and record.status == 415
    assert not hasattr(record, "compatibility")
    assert_absent(caplog, SECRET_FILENAME, "SECRETNAME")


def test_parser_crash_logs_exception_type_and_code_never_its_text(monkeypatch, caplog):
    def crash(path):
        raise ValueError(f"bad cell '{SECRET_VALUE}' in {SECRET_FILENAME} at /srv/secret/dir")

    monkeypatch.setattr(api, "profile_file", crash)
    with caplog.at_level(logging.DEBUG, logger="bearing_pdm.api"):
        response = client.post(
            "/dataset/inspect", files=multipart_file(SECRET_FILENAME, b"vibration_x\n1\n2\n3\n")
        )
    assert response.status_code == 422
    record = only_record(caplog)
    assert record.code == "MALFORMED_FILE" and record.exc_type == "ValueError"
    assert "exc_type=ValueError" in record.getMessage()
    assert_absent(caplog, SECRET_VALUE, SECRET_FILENAME, "/srv/secret")


def test_unhandled_exception_is_a_warning_with_type_and_no_traceback(monkeypatch, caplog):
    def boom(name):
        raise RuntimeError(f"internal path /srv/secret and value {SECRET_VALUE}")

    monkeypatch.setattr(api, "_load_joblib", boom)
    with caplog.at_level(logging.DEBUG, logger="bearing_pdm.api"):
        response = client.get("/health")
    assert response.status_code == 500
    record = only_record(caplog)
    assert record.code == "INTERNAL_ERROR" and record.exc_type == "RuntimeError"
    assert record.levelno == logging.WARNING and record.request_id == response.headers["X-Request-ID"]
    assert all(r.exc_info is None for r in caplog.records)
    assert_absent(caplog, "/srv/secret", SECRET_VALUE, "Traceback")


def test_body_too_large_is_logged_with_its_code(caplog):
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.post(
            "/dataset/inspect",
            content=b"x",
            headers={"Content-Length": str(api._MAX_REQUEST_BYTES + 1),
                     "Content-Type": "multipart/form-data; boundary=b"},
        )
    assert response.status_code == 413
    record = only_record(caplog)
    assert record.code == "REQUEST_TOO_LARGE" and record.stage == "dataset_inspect"


def test_history_write_failure_is_coded_and_typed(monkeypatch, caplog):
    class Broken:
        limit = 1

        def append(self, record):
            raise OSError(f"disk full at /srv/secret {SECRET_VALUE}")

        def recent(self):
            return []

    monkeypatch.setattr(api, "_history_store", Broken())
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.post("/predict/rul", json={"dataset_id": "college", "features": {}})
    assert response.status_code == 503
    record = only_record(caplog)
    assert record.code == "HISTORY_UNAVAILABLE" and record.exc_type == "OSError"
    assert_absent(caplog, "/srv/secret", SECRET_VALUE)


# --- /health ---------------------------------------------------------------

@pytest.mark.skipif(not (MODEL_PRESENT and HI_MODEL_PRESENT), reason="trained artifacts not present")
def test_health_reports_model_versions_without_paths():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["ready"] is True
    assert body["api_version"] == api.app.version
    assert body["models_loaded"]["rul_extra_trees"] is True
    for name in ("rul_extra_trees", "reference_hi"):
        info = body["models"][name]
        assert info["loaded"] is True
        assert info["version"].startswith("sha256:")
        assert info["feature_schema_version"].startswith("sha256:")
    version, schema = api._model_provenance("predict_rul", "rul_extra_trees.joblib")
    assert body["models"]["rul_extra_trees"]["version"] == version
    assert body["models"]["rul_extra_trees"]["feature_schema_version"] == schema
    text = str(body)
    assert str(api.REPO_ROOT) not in text and str(api.MODELS_DIR) not in text
    assert ".joblib" not in text and "/" not in text.replace("sha256:", "")


def test_health_reports_missing_models_as_not_ready_not_as_an_error(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "MANIFEST_PATH", tmp_path / "manifest.json")  # no real source_url to fall back to - genuinely unavailable, not just locally missing
    monkeypatch.setattr(api, "_MODEL_CACHE", {})
    monkeypatch.setattr(api, "_MODEL_VERSIONS", {})
    with caplog.at_level(logging.INFO, logger="bearing_pdm.api"):
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["ready"] is False
    assert body["models_loaded"] == {"rul_extra_trees": False, "rul_naive": False}
    for name in ("rul_extra_trees", "reference_hi"):
        assert body["models"][name] == {
            "loaded": False, "version": None, "feature_schema_version": None,
        }
    assert str(tmp_path) not in str(body)
    assert str(tmp_path) not in caplog.text
