"""Public contract snapshot and gaps; existing regression owners are in docs/api-errors.md.

Regenerate deliberately with: python tests/test_api_contract.py --write-snapshot
"""

import argparse
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException
from starlette.requests import Request

from bearing_pdm import api, chunked
from bearing_pdm.history import InMemoryHistoryStore

SNAPSHOT = Path(__file__).parent / "fixtures" / "api_openapi.json"


def public_schema():
    # Generate afresh: app.openapi() caches and can conceal a changed route/model.
    return get_openapi(title=api.app.title, version=api.app.version, routes=api.app.routes,
                       description=api.app.description, openapi_version=api.app.openapi_version)


def test_public_openapi_contract():
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert public_schema() == expected, (
        "Public API contract changed. Review the schema diff and follow "
        "docs/api-errors.md before deliberately regenerating api_openapi.json."
    )


@pytest.mark.parametrize("path,fields", [
    ("/health", {"status", "models_loaded", "models", "ready", "api_version"}),
    ("/models/info", {"selected_model", "extra_trees_feature_columns", "hi_feature_columns",
                      "supported_datasets", "note"}),
    ("/predictions/history", {"count", "limit", "predictions"}),
])
def test_untyped_response_fields(path, fields, monkeypatch):
    # These dictionary responses have no named properties in OpenAPI.
    monkeypatch.setattr(api, "_history_store", InMemoryHistoryStore(2))
    response = TestClient(api.app).get(path)
    assert response.status_code == 200
    assert set(response.json()) == fields
    if path == "/health":
        body = response.json()
        assert set(body["models_loaded"]) == {"rul_extra_trees", "rul_naive"}
        assert set(body["models"]) == {"rul_extra_trees", "reference_hi"}
        for model in body["models"].values():
            assert set(model) == {"loaded", "version", "feature_schema_version"}


@pytest.mark.parametrize("csv,state,action", [
    pytest.param(b"vibration_z\n1\n2\n3\n", "FULLY_SUPPORTED", "STRUCTURAL_CHECK_ONLY",
                 id="vibration-z-only"),
    pytest.param(b"vibration_x,vibration_y\n1,2\n", "INVALID_INPUT", "FIX_INPUT_FILE",
                 id="header-plus-one-row"),
])
def test_inspect_reviewer_regressions(csv, state, action, tmp_path):
    # Structural verdict (shared by /analyze/features and /dataset/inspect).
    path = tmp_path / "regression.csv"
    path.write_bytes(csv)
    structural_state, structural_reasons, structural_action = api._classify_detailed(
        api.profile_file(path))
    assert (structural_state, structural_action["kind"]) == (state, action)
    if state == "FULLY_SUPPORTED":
        assert structural_reasons == []
        assert "NOT mean a trained model is validated" in structural_action["message"]

    # /dataset/inspect adds the metadata gate: a structurally usable file with no
    # sampling rate or units is never reported FULLY_SUPPORTED.
    response = TestClient(api.app).post(
        "/dataset/inspect", files={"file": ("regression.csv", csv, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert "code" not in body
    assert body["reasons"]
    if state == "FULLY_SUPPORTED":
        assert body["compatibility"] == "ADAPTER_REQUIRED"
        assert body["required_action"]["kind"] == "METADATA_REQUIRED"
        assert body["sampling"]["rate_hz"] is None
    else:
        assert (body["compatibility"], body["required_action"]["kind"]) == (state, action)


@pytest.mark.parametrize("status,code,retryable", [
    (408, "REQUEST_TIMEOUT", True),
    (429, "RATE_LIMITED", True),
    (504, "GATEWAY_TIMEOUT", True),
    (503, "SERVICE_UNAVAILABLE", True),
    (418, "HTTP_ERROR", False),
])
def test_framework_error_defaults(status, code, retryable):
    # Framework defaults are not emitted by a public route today. Exercise the
    # registered handler without adding test-only routes to the production app.
    request = Request({"type": "http", "method": "GET", "path": "/health", "headers": []})
    handler = api.app.exception_handlers[HTTPException]
    response = asyncio.run(handler(request, HTTPException(
        status, "Framework rejection", headers={"Retry-After": "3"})))
    assert response.status_code == status
    assert json.loads(response.body) == {
        "code": code, "retryable": retryable,
        "detail": "Framework rejection", "message": "Framework rejection",
    }
    assert response.headers["Retry-After"] == "3"


@pytest.mark.parametrize("failure,status", [("parser", 422), ("window-count", 500)])
def test_feature_extraction_failure_contract(failure, status, monkeypatch, caplog):
    def broken_stream(*args, **kwargs):
        if failure == "parser":
            raise ValueError("private sensor content")
        yield from ()

    monkeypatch.setattr(chunked, "iter_csv_window_features", broken_stream)
    response = TestClient(api.app).post(
        "/analyze/features",
        params={"channel": "vibration_x", "sampling_rate_hz": 8, "window_samples": 8},
        files={"file": ("synthetic.csv", b"vibration_x\n1\n2\n3\n2\n1\n2\n3\n2\n")},
    )
    assert response.status_code == status, response.text
    body = response.json()
    assert body["code"] == "FEATURE_EXTRACTION_FAILED"
    assert body["retryable"] is False
    assert body["failed_stage"] == "feature_extraction"
    assert body["message"] == body["detail"]
    assert "private sensor content" not in response.text
    assert "private sensor content" not in caplog.text
    assert "windows" not in body
    assert any(s["name"] == "feature_extraction" and s["status"] == "failed"
               for s in body["stages"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-snapshot", action="store_true", required=True)
    parser.parse_args()
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(public_schema(), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
