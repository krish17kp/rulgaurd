"""Error contract of the API (docs/api-errors.md): every error body keeps
`detail` and adds a stable `code`, a `retryable` bool and a readable `message`;
malformed uploads never produce a 500 or a traceback."""

from __future__ import annotations

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api, artifacts

client = TestClient(api.app, raise_server_exceptions=False)
ORIGIN = api._ALLOWED_ORIGINS[0]
CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")


def assert_error(response, status: int, code: str, retryable: bool = False) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert "detail" in body
    assert body["code"] == code
    assert CODE_PATTERN.match(body["code"])
    assert body["retryable"] is retryable
    assert isinstance(body["message"], str) and body["message"]
    assert "Traceback" not in response.text
    return body


def multipart(csv_bytes: bytes) -> tuple[bytes, str]:
    boundary = "errboundary42"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="x.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n"
    ).encode() + csv_bytes + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def chunks(body: bytes, size: int):
    for i in range(0, len(body), size):
        yield body[i : i + size]


def upload(data: bytes, **kwargs):
    return client.post("/dataset/inspect", files={"file": ("x.csv", data, "text/csv")}, **kwargs)


# --- 413 -------------------------------------------------------------------

def test_content_length_413_has_code_cors_and_request_id():
    response = client.post(
        "/predict/hi",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(api._MAX_REQUEST_BYTES + 1),
            "Origin": ORIGIN,
        },
    )
    assert_error(response, 413, "REQUEST_TOO_LARGE")
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()
    assert response.headers["X-Request-ID"]


def test_chunked_413_has_code_cors_and_request_id(monkeypatch):
    monkeypatch.setattr(api, "_MAX_REQUEST_BYTES", 1024)
    body, content_type = multipart(b"vibration_x\n" + b"1.0\n" * 2000)
    response = client.post(
        "/dataset/inspect",
        content=chunks(body, 256),
        headers={"Content-Type": content_type, "Origin": ORIGIN},
    )
    assert_error(response, 413, "REQUEST_TOO_LARGE")
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["X-Request-ID"]


def test_file_limit_413_is_upload_too_large(monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 10)
    body = assert_error(upload(b"vibration_x\n" + b"1.0\n" * 100), 413, "UPLOAD_TOO_LARGE")
    assert "inspection limit" in body["detail"]


# --- 422 / 400 validation --------------------------------------------------

def test_body_validation_error_keeps_detail_list_and_adds_code():
    response = client.post("/predict/rul", json={"features": {}})
    body = assert_error(response, 422, "VALIDATION_ERROR")
    assert isinstance(body["detail"], list) and body["detail"][0]["loc"]
    assert "dataset_id" in body["message"]


@pytest.mark.parametrize("rate", ["abc", "-5", "0", "nan", "inf"])
def test_invalid_sampling_rate_is_validation_error(rate):
    response = client.post("/dataset/inspect", data={"declared_sampling_rate_hz": rate},
                           files={"file": ("x.csv", b"vibration_x\n1\n2\n3\n", "text/csv")})
    assert_error(response, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("path", [
    "/models/compatibility",
    "/analyze/rul?dataset_id=femto&units=g&preprocessing_version=femto-acquisition-v1",
])
def test_non_finite_json_body_is_422_not_500(path, literal):
    # Literal tokens in the raw body: Python's JSON parser accepts them, and the
    # echoed `input` must not make the error response itself unserialisable.
    body = ('{"dataset_id": "femto", "feature_names": ["a"], "sampling_rate_hz": %s}'
            % literal).encode()
    response = client.post(path, content=body, headers={"Content-Type": "application/json"})
    assert_error(response, 422, "VALIDATION_ERROR")

    def reject(token):
        raise AssertionError(f"non-standard JSON token {token} in error body")

    json.loads(response.text, parse_constant=reject)


def test_missing_file_part_is_validation_error():
    response = client.post("/dataset/inspect", files={"other": ("a.csv", b"x", "text/csv")})
    assert_error(response, 422, "VALIDATION_ERROR")


def test_malformed_json_is_validation_error():
    response = client.post("/predict/rul", content=b"{bad", headers={"Content-Type": "application/json"})
    assert_error(response, 422, "VALIDATION_ERROR")


def test_malformed_multipart_body_is_400_with_code():
    response = client.post(
        "/dataset/inspect", content=b"junk", headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code in (400, 422)
    body = response.json()
    assert body["code"] in {"MALFORMED_REQUEST", "VALIDATION_ERROR"}
    assert body["retryable"] is False


def test_unknown_route_and_wrong_method_have_codes():
    assert_error(client.get("/no/such/route"), 404, "NOT_FOUND")
    assert_error(client.put("/health"), 405, "METHOD_NOT_ALLOWED")


@pytest.mark.parametrize("path", ["/predict/rul", "/predict/hi"])
def test_unsupported_dataset_has_code(path):
    payload = {"dataset_id": "college", "features": {}} if path.endswith("rul") else {
        "dataset_id": "college", "rows": [{"sequence_index": 0}],
    }
    body = assert_error(client.post(path, json=payload), 422, "UNSUPPORTED_DATASET")
    assert "femto" in body["detail"].lower()


# --- 503 -------------------------------------------------------------------

@pytest.fixture
def no_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(api, "METRICS_DIR", tmp_path)
    monkeypatch.setattr(api, "_MODEL_CACHE", {})


def test_missing_rul_model_is_retryable_503(no_artifacts):
    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": {}})
    assert_error(response, 503, "MODEL_UNAVAILABLE", retryable=True)


def test_missing_hi_artifacts_is_retryable_503(no_artifacts):
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": [{"sequence_index": 0}]})
    assert_error(response, 503, "MODEL_UNAVAILABLE", retryable=True)


def test_missing_metrics_file_is_retryable_503(no_artifacts):
    assert_error(client.get("/models/evaluation"), 503, "METRICS_UNAVAILABLE", retryable=True)


def test_upload_spool_failure_is_retryable_503(monkeypatch):
    def broken(head):
        raise OSError("No space left on device")

    monkeypatch.setattr(api, "_check_text_head", broken)
    assert_error(upload(b"vibration_x\n1\n2\n3\n"), 503, "STORAGE_UNAVAILABLE", retryable=True)


def test_memory_error_during_inspection_is_503_not_retryable(monkeypatch):
    def out_of_memory(path):
        raise MemoryError

    monkeypatch.setattr(api, "profile_file", out_of_memory)
    assert_error(upload(b"vibration_x\n1\n2\n3\n"), 503, "MEMORY_LIMIT_EXCEEDED")


# --- malformed uploads -----------------------------------------------------

def test_empty_upload_code():
    assert_error(upload(b""), 422, "EMPTY_UPLOAD")


@pytest.mark.parametrize(
    "data",
    [
        b"vibration_x,vibration_y\n1,2\x00\n3,4\n5,6\n",
        b"\x00" * 200,
        b"PK\x03\x04" + b"vibration_x\n1\n2\n",
        b"%PDF-1.7 vibration_x\n1\n",
        b"\x1f\x8b\x08\x00vibration_x",
    ],
)
def test_binary_upload_is_415(data):
    assert_error(upload(data), 415, "UNSUPPORTED_FILE_TYPE")


@pytest.mark.parametrize(
    "data",
    [
        b"\xff\xfe\xfd\n\xff\xfe\n",
        b"vibration_x\n1.0\n\xe9\n2.0\n",
        bytes(range(128, 256)) * 20,
    ],
)
def test_undecodable_upload_is_422(data):
    assert_error(upload(data), 422, "UNDECODABLE_FILE")


def test_huge_single_line_is_rejected_without_being_parsed(monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_CHUNK_BYTES", 1024)

    def must_not_parse(path):
        raise AssertionError("profile_file must not see a file with a giant first line")

    monkeypatch.setattr(api, "profile_file", must_not_parse)
    assert_error(upload(b"a," * 5000), 422, "MALFORMED_FILE")


def test_short_single_line_file_is_not_treated_as_a_giant_line():
    response = upload(b"vibration_x,vibration_y")
    assert response.status_code == 200
    assert response.json()["compatibility"] == "INVALID_INPUT"


def test_parser_crash_is_422_and_never_leaks_cell_values(monkeypatch, caplog):
    def crash(path):
        raise ValueError("bad cell 'SECRET-SENSOR-READING-0.123'")

    monkeypatch.setattr(api, "profile_file", crash)
    with caplog.at_level(logging.DEBUG, logger="bearing_pdm.api"):
        response = upload(b"vibration_x\n1\n2\n3\n")
    assert_error(response, 422, "MALFORMED_FILE")
    assert "SECRET-SENSOR-READING" not in response.text
    assert "SECRET-SENSOR-READING" not in caplog.text


@pytest.mark.parametrize(
    "data",
    [
        b"\n1,2\n3,4\n",
        b",,,\n,,,\n",
        b"   \n  \n",
        b"vibration_x,vibration_y\n1,2,3,4\n5\n6,7\n",
        b'vibration_x,"vib\n1\n2\n',
        b"vibration_x,vibration_x\n1,2\n3,4\n5,7\n",
        b"\xef\xbb\xbfvibration_x\n1\n2\n3\n",
        b"vibration_x\n" + b"9" * 200_000 + b"\n1\n",
        b"\r\r\r\r",
    ],
)
def test_malformed_csv_never_returns_5xx_or_traceback(data):
    response = upload(data)
    assert response.status_code < 500, response.text
    assert "Traceback" not in response.text
    body = response.json()
    if response.status_code == 200:
        assert body["compatibility"] in {"INVALID_INPUT", "UNSUPPORTED", "ADAPTER_REQUIRED", "FULLY_SUPPORTED"}
    else:
        assert CODE_PATTERN.match(body["code"]) and body["retryable"] is False


# --- last-resort boundary --------------------------------------------------

def test_unhandled_exception_is_json_500_with_cors_and_no_traceback(monkeypatch, caplog):
    def boom(name):
        raise RuntimeError("internal path /srv/secret and value 0.987")

    monkeypatch.setattr(api, "_load_joblib", boom)
    with caplog.at_level(logging.DEBUG, logger="bearing_pdm.api"):
        response = client.get("/health", headers={"Origin": ORIGIN})
    body = assert_error(response, 500, "INTERNAL_ERROR")
    assert body["detail"] == "Internal server error."
    assert "/srv/secret" not in response.text
    assert "/srv/secret" not in caplog.text
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["X-Request-ID"]


def test_success_responses_are_unchanged():
    response = client.get("/health")
    assert response.status_code == 200
    assert "code" not in response.json()
