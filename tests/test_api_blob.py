"""Direct-to-storage (Vercel Blob) upload path: bounded-memory chunked
download, lifecycle cleanup, and - the scientifically load-bearing claim -
that the blob path produces byte-identical results to the trusted
direct-multipart-upload reference path on the same real fixture bytes
(ml-data.md: a chunked/alternate path must match the trusted pipeline).
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"
FEMTO_ACQ = FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv"

client = TestClient(api.app)
MODEL_PRESENT = (api.MODELS_DIR / "rul_extra_trees.joblib").exists()


def _mock_client_serving(content: bytes, *, status_code: int = 200) -> httpx.Client:
    """A fake Vercel Blob object server: same bytes, every request - the
    seam tests substitute for a real network call via api._get_http_client."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=content)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_stream_blob_to_tempfile_reassembles_multiple_chunks_byte_exact(monkeypatch, tmp_path):
    """The real FEMTO fixture (~78KB) is smaller than UPLOAD_CHUNK_BYTES
    (1MB), so the parity tests below never actually exercise more than one
    iteration of _stream_blob_to_tempfile's chunk loop - found in review.
    This proves multi-chunk reassembly directly, decoupled from CSV parsing."""
    # Random but text-shaped (hex lines): blob downloads get the same text-head
    # check as direct uploads, so binary bytes would be rejected before reassembly.
    content = b"\n".join(
        os.urandom(32).hex().encode() for _ in range((3 * api.UPLOAD_CHUNK_BYTES + 12345) // 65 + 1)
    )
    assert len(content) > 3 * api.UPLOAD_CHUNK_BYTES  # spans 4 chunk reads
    monkeypatch.setattr(api, "_get_http_client", lambda: _mock_client_serving(content))

    tmp_file = tmp_path / "blob_download"
    with tmp_file.open("wb") as tmp:
        written = api._stream_blob_to_tempfile("https://x.blob.vercel-storage.com/x", tmp, len(content))

    assert written == len(content)
    assert tmp_file.read_bytes() == content


@pytest.fixture
def blob_url(monkeypatch):
    monkeypatch.setenv("ALLOW_LOCAL_BLOB_HOSTS", "1")
    return "http://localhost/fake-blob/acc_00001.csv"


def test_rejects_non_blob_host_url():
    response = client.post(
        "/predict/rul/femto-acquisition/blob", json={"blob_url": "https://evil.example.com/x.csv"}
    )
    assert response.status_code == 422
    assert "blob_url" in response.json()["detail"]


@pytest.mark.skipif(not MODEL_PRESENT, reason="artifacts/models/rul_extra_trees.joblib not present")
def test_blob_femto_path_matches_direct_multipart_reference(blob_url, monkeypatch):
    content = FEMTO_ACQ.read_bytes()

    deleted_urls: list[str] = []
    monkeypatch.setattr(api, "_get_http_client", lambda: _mock_client_serving(content))
    monkeypatch.setattr(
        api, "_delete_blob", lambda url: deleted_urls.append(url)
    )

    with FEMTO_ACQ.open("rb") as fh:
        reference = client.post(
            "/predict/rul/femto-acquisition",
            files={"file": ("acc_00001.csv", fh, "text/csv")},
        )
    assert reference.status_code == 200

    via_blob = client.post("/predict/rul/femto-acquisition/blob", json={"blob_url": blob_url})
    assert via_blob.status_code == 200

    ref_body, blob_body = reference.json(), via_blob.json()
    assert blob_body["rul_seconds"] == ref_body["rul_seconds"]
    assert blob_body["rul_hours"] == ref_body["rul_hours"]
    assert blob_body["features_used"] == ref_body["features_used"]
    assert blob_body["features_missing"] == ref_body["features_missing"]
    assert deleted_urls == [blob_url]


def test_blob_inspect_path_matches_direct_multipart_reference(blob_url, monkeypatch):
    content = FEMTO_ACQ.read_bytes()
    monkeypatch.setattr(api, "_get_http_client", lambda: _mock_client_serving(content))
    monkeypatch.setattr(api, "_delete_blob", lambda url: None)

    with FEMTO_ACQ.open("rb") as fh:
        reference = client.post("/dataset/inspect", files={"file": ("acc_00001.csv", fh, "text/csv")})
    assert reference.status_code == 200

    via_blob = client.post("/dataset/inspect/blob", json={"blob_url": blob_url})
    assert via_blob.status_code == 200
    assert via_blob.json()["compatibility"] == reference.json()["compatibility"]
    assert via_blob.json()["reasons"] == reference.json()["reasons"]


def test_missing_blob_object_returns_404(blob_url, monkeypatch):
    monkeypatch.setattr(api, "_get_http_client", lambda: _mock_client_serving(b"", status_code=404))
    response = client.post("/predict/rul/femto-acquisition/blob", json={"blob_url": blob_url})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_interrupted_download_returns_502(blob_url, monkeypatch):
    class _BrokenClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, *args, **kwargs):
            raise httpx.ReadError("connection reset")

    monkeypatch.setattr(api, "_get_http_client", lambda: _BrokenClient())
    response = client.post("/predict/rul/femto-acquisition/blob", json={"blob_url": blob_url})
    assert response.status_code == 502
    assert "interrupted" in response.json()["detail"].lower()


def test_oversized_blob_object_returns_413(blob_url, monkeypatch):
    oversized = b"0\n" * ((api.MAX_UPLOAD_BYTES + 1024) // 2)
    monkeypatch.setattr(api, "_get_http_client", lambda: _mock_client_serving(oversized))
    response = client.post("/predict/rul/femto-acquisition/blob", json={"blob_url": blob_url})
    assert response.status_code == 413
    assert response.json()["code"] == "UPLOAD_TOO_LARGE"


@pytest.mark.parametrize("content, status, code", [
    (b"PK\x03\x04binary", 415, "UNSUPPORTED_FILE_TYPE"),
    (b"\xff\xfe\xfa,b\n1,2\n", 422, "UNDECODABLE_FILE"),
])
@pytest.mark.parametrize("route", ["/predict/rul/femto-acquisition/blob", "/dataset/inspect/blob"])
def test_blob_download_gets_the_same_text_checks_as_a_direct_upload(
        blob_url, monkeypatch, content, status, code, route):
    """Regression: a binary or non-UTF-8 object fetched from storage was
    profiled as if it were text (a misleading 200 profile) instead of being
    rejected the way the same bytes are on the direct-upload path."""
    deleted: list[str] = []
    monkeypatch.setattr(api, "_get_http_client", lambda: _mock_client_serving(content))
    monkeypatch.setattr(api, "_delete_blob", lambda url: deleted.append(url))
    response = client.post(route, json={"blob_url": blob_url})
    assert response.status_code == status
    assert response.json()["code"] == code
    assert deleted == [blob_url]


def test_empty_blob_object_returns_422(blob_url, monkeypatch):
    monkeypatch.setattr(api, "_get_http_client", lambda: _mock_client_serving(b""))
    response = client.post("/predict/rul/femto-acquisition/blob", json={"blob_url": blob_url})
    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_delete_blob_logs_but_does_not_raise_on_an_error_response(monkeypatch):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "fake-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    monkeypatch.setattr(
        api, "_get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    api._delete_blob("https://example.public.blob.vercel-storage.com/x.csv")  # must not raise


def test_delete_blob_failure_log_never_contains_the_url(monkeypatch, caplog):
    # The URL carries the uploaded filename; observability.md forbids filenames in logs.
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "fake-token")
    monkeypatch.setattr(
        api, "_get_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )
    with caplog.at_level("DEBUG", logger="bearing_pdm.api"):
        api._delete_blob("https://example.public.blob.vercel-storage.com/patient-SECRET.csv")
    assert "returned 500" in caplog.text
    assert "SECRET" not in caplog.text and "fake-token" not in caplog.text


def test_delete_blob_is_best_effort_on_a_transport_error(monkeypatch):
    """httpx.Client.post doesn't raise on a 4xx/5xx body (covered above) -
    this exercises the actual `except httpx.HTTPError` branch, which only a
    real transport failure (not an HTTP error status) triggers."""
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "fake-token")

    class _BrokenClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError("refused")

    monkeypatch.setattr(api, "_get_http_client", lambda: _BrokenClient())
    api._delete_blob("https://example.public.blob.vercel-storage.com/x.csv")  # must not raise


def test_delete_blob_noop_without_token(monkeypatch):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    calls = []
    monkeypatch.setattr(api, "_get_http_client", lambda: calls.append(1) or httpx.Client())
    api._delete_blob("https://example.public.blob.vercel-storage.com/x.csv")
    assert calls == []


def test_blob_is_deleted_even_when_the_download_itself_fails(blob_url, monkeypatch):
    """Review found cleanup previously only wrapped the processing step, so
    a download-time failure (here: 404) left the blob behind forever."""
    deleted: list[str] = []
    monkeypatch.setattr(api, "_get_http_client", lambda: _mock_client_serving(b"", status_code=404))
    monkeypatch.setattr(api, "_delete_blob", lambda url: deleted.append(url))

    response = client.post("/predict/rul/femto-acquisition/blob", json={"blob_url": blob_url})
    assert response.status_code == 404
    assert deleted == [blob_url]


def test_rejects_control_characters_hidden_in_the_url():
    # urlsplit silently drops \t/\r/\n from a hostname instead of erroring -
    # this crafted URL would otherwise reach httpx with a tab stripped out
    # of "evil.com" + ".blob.vercel-storage.com", passing the suffix check.
    response = client.post(
        "/predict/rul/femto-acquisition/blob",
        json={"blob_url": "https://evil.com\t.blob.vercel-storage.com/x.csv"},
    )
    assert response.status_code == 422


def test_pinned_blob_store_hostname_rejects_other_vercel_customers_stores(monkeypatch):
    monkeypatch.setenv("BLOB_STORE_HOSTNAME", "myproject123.public.blob.vercel-storage.com")
    response = client.post(
        "/predict/rul/femto-acquisition/blob",
        json={"blob_url": "https://someoneelse456.public.blob.vercel-storage.com/x.csv"},
    )
    assert response.status_code == 422


def test_pinned_blob_store_hostname_accepts_its_own_store(monkeypatch):
    monkeypatch.setenv("BLOB_STORE_HOSTNAME", "myproject123.public.blob.vercel-storage.com")
    monkeypatch.setattr(api, "_get_http_client", lambda: _mock_client_serving(b"not empty"))
    monkeypatch.setattr(api, "_delete_blob", lambda url: None)
    response = client.post(
        "/predict/rul/femto-acquisition/blob",
        json={"blob_url": "https://myproject123.public.blob.vercel-storage.com/x.csv"},
    )
    # Fails on content (not a real FEMTO CSV), not on the host check -
    # proves the pinned hostname was accepted rather than rejected.
    assert "blob_url" not in response.json().get("detail", "")
