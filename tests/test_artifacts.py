"""artifacts.py: the production artifact-delivery loader. Verifies the
checksum-or-refuse contract (ml-data.md: never load an unverified/wrong
artifact) and that it never buffers a download unbounded (python.md)."""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from bearing_pdm import artifacts


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Points MODELS_DIR/MANIFEST_PATH/_cache_dir at a scratch directory so
    tests never touch the real artifacts/models/ (which has real,
    multi-hundred-MB files) or leave cache files behind."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(artifacts, "MODELS_DIR", models_dir)
    monkeypatch.setattr(artifacts, "MANIFEST_PATH", models_dir / "manifest.json")
    monkeypatch.setenv("ARTIFACT_CACHE_DIR", str(cache_dir))
    return models_dir


def _mock_client(content: bytes, *, status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=content)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_load_manifest_missing_file_returns_empty(isolated_dirs):
    assert artifacts.load_manifest() == {}


def test_load_manifest_malformed_json_returns_empty_not_raises(isolated_dirs):
    artifacts.MANIFEST_PATH.write_text("{not valid json")
    assert artifacts.load_manifest() == {}


def test_ensure_artifact_uses_local_file_without_touching_network(isolated_dirs, monkeypatch):
    local = isolated_dirs / "model.joblib"
    local.write_bytes(b"real local artifact")
    monkeypatch.setattr(artifacts, "_get_http_client", lambda: (_ for _ in ()).throw(AssertionError("no network")))

    result = artifacts.ensure_artifact("model.joblib")
    assert result == local


def test_ensure_artifact_returns_none_without_manifest_entry(isolated_dirs):
    assert artifacts.ensure_artifact("nonexistent.joblib") is None


def test_ensure_artifact_returns_none_when_manifest_entry_has_no_source_url(isolated_dirs):
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({"artifacts": {"model.joblib": {"sha256": "x", "source_url": None}}})
    )
    assert artifacts.ensure_artifact("model.joblib") is None


def test_ensure_artifact_downloads_and_verifies_a_matching_checksum(isolated_dirs, monkeypatch):
    content = b"a trained model, hypothetically"
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({
            "artifacts": {
                "model.joblib": {
                    "sha256": _sha256(content),
                    "source_url": "https://example.com/model.joblib",
                }
            }
        })
    )
    monkeypatch.setattr(artifacts, "_get_http_client", lambda: _mock_client(content))

    result = artifacts.ensure_artifact("model.joblib")
    assert result is not None
    assert result.read_bytes() == content


def test_ensure_artifact_refuses_a_checksum_mismatch(isolated_dirs, monkeypatch):
    content = b"attacker-controlled or corrupted bytes"
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({
            "artifacts": {
                "model.joblib": {
                    "sha256": _sha256(b"the real expected content"),
                    "source_url": "https://example.com/model.joblib",
                }
            }
        })
    )
    monkeypatch.setattr(artifacts, "_get_http_client", lambda: _mock_client(content))

    result = artifacts.ensure_artifact("model.joblib")
    assert result is None
    # No half-verified file left sitting where a later call might trust it.
    assert not list(artifacts._cache_dir().glob("model.joblib*"))


def test_ensure_artifact_uses_a_previously_verified_cache_without_refetching(isolated_dirs, monkeypatch):
    content = b"cached artifact bytes"
    sha = _sha256(content)
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({"artifacts": {"model.joblib": {"sha256": sha, "source_url": "https://example.com/x"}}})
    )
    cached = artifacts._cache_dir() / "model.joblib"
    cached.write_bytes(content)

    monkeypatch.setattr(artifacts, "_get_http_client", lambda: (_ for _ in ()).throw(AssertionError("no network")))
    result = artifacts.ensure_artifact("model.joblib")
    assert result == cached


def test_ensure_artifact_refetches_a_stale_cache_that_no_longer_matches(isolated_dirs, monkeypatch):
    good_content = b"the current correct bytes"
    stale_cached = b"an old/corrupted cached copy"
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({
            "artifacts": {
                "model.joblib": {"sha256": _sha256(good_content), "source_url": "https://example.com/x"}
            }
        })
    )
    cached = artifacts._cache_dir() / "model.joblib"
    cached.write_bytes(stale_cached)
    monkeypatch.setattr(artifacts, "_get_http_client", lambda: _mock_client(good_content))

    result = artifacts.ensure_artifact("model.joblib")
    assert result is not None
    assert result.read_bytes() == good_content


def _no_leftover_temp_files():
    """No partial-download file of any name was left in the cache dir -
    review found the original cleanup only fired when the download was
    completely empty, leaving a full-sized `.part` file on every
    oversized/interrupted failure."""
    return not list(artifacts._cache_dir().glob(".*.part"))


def test_download_rejects_an_oversized_object_and_cleans_up(isolated_dirs, monkeypatch):
    oversized = b"0" * (1024)
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({
            "artifacts": {"model.joblib": {"sha256": _sha256(oversized), "source_url": "https://example.com/x"}}
        })
    )
    monkeypatch.setattr(artifacts, "MAX_ARTIFACT_BYTES", 100)
    monkeypatch.setattr(artifacts, "_get_http_client", lambda: _mock_client(oversized))

    assert artifacts.ensure_artifact("model.joblib") is None
    assert _no_leftover_temp_files()


def test_download_handles_an_interrupted_transfer_and_cleans_up(isolated_dirs, monkeypatch):
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({"artifacts": {"model.joblib": {"sha256": "x", "source_url": "https://example.com/x"}}})
    )

    class _BrokenClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, *args, **kwargs):
            raise httpx.ReadError("connection reset")

    monkeypatch.setattr(artifacts, "_get_http_client", lambda: _BrokenClient())
    assert artifacts.ensure_artifact("model.joblib") is None
    assert _no_leftover_temp_files()


def test_download_handles_a_404_from_the_source(isolated_dirs, monkeypatch):
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({"artifacts": {"model.joblib": {"sha256": "x", "source_url": "https://example.com/x"}}})
    )
    monkeypatch.setattr(artifacts, "_get_http_client", lambda: _mock_client(b"", status_code=404))
    assert artifacts.ensure_artifact("model.joblib") is None
    assert _no_leftover_temp_files()


def test_download_treats_a_redirect_as_a_failure_not_as_content(isolated_dirs, monkeypatch):
    """A 302 (e.g. a real GitHub Release asset URL) must never have its
    body written out and mistaken for the artifact, or misreported as a
    checksum mismatch - review found the original >=400 check let any 3xx
    straight through as if it were a successful 200."""
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({"artifacts": {"model.joblib": {"sha256": "x", "source_url": "https://example.com/x"}}})
    )
    monkeypatch.setattr(artifacts, "_get_http_client", lambda: _mock_client(b"", status_code=302))
    assert artifacts.ensure_artifact("model.joblib") is None
    assert _no_leftover_temp_files()


def test_ensure_artifact_rejects_path_traversal_in_the_name(isolated_dirs):
    assert artifacts.ensure_artifact("../../../../etc/passwd") is None
    assert artifacts.ensure_artifact("sub/dir.joblib") is None


def test_ensure_artifact_never_trusts_a_cached_file_with_no_manifest_entry(isolated_dirs):
    """Review found: a missing/broken manifest previously made every file
    already sitting in the cache directory trusted unconditionally - a
    real risk on a shared /tmp another process could have written into
    first. A cached file with nothing to check it against must be
    refused, not silently loaded."""
    planted = artifacts._cache_dir() / "model.joblib"
    planted.write_bytes(b"planted by something else entirely")
    # No manifest entry at all for "model.joblib".
    assert artifacts.ensure_artifact("model.joblib") is None


def test_ensure_artifact_never_trusts_a_cached_file_when_manifest_entry_has_no_sha256(isolated_dirs):
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({"artifacts": {"model.joblib": {"sha256": None, "source_url": None}}})
    )
    planted = artifacts._cache_dir() / "model.joblib"
    planted.write_bytes(b"planted by something else entirely")
    assert artifacts.ensure_artifact("model.joblib") is None


def test_concurrent_requests_for_the_same_artifact_download_only_once(isolated_dirs, monkeypatch):
    """FastAPI's sync `def` endpoints run in a thread pool, so two requests
    for the same cold-start-missing artifact can genuinely race. Review
    found they could previously interleave writes into one shared temp
    file; _lock_for(name) now serializes them, and each should still get
    back a valid, checksum-matching path - not one success and one
    spurious None."""
    import threading
    import time

    content = b"the one true artifact content"
    artifacts.MANIFEST_PATH.write_text(
        json.dumps({
            "artifacts": {"model.joblib": {"sha256": _sha256(content), "source_url": "https://example.com/x"}}
        })
    )
    call_count = 0
    call_lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        with call_lock:
            call_count += 1
        time.sleep(0.05)  # widen the race window
        return httpx.Response(200, content=content)

    monkeypatch.setattr(
        artifacts, "_get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )

    results: list[object] = [None, None]

    def worker(i: int) -> None:
        results[i] = artifacts.ensure_artifact("model.joblib")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r is not None for r in results), results
    assert all(r.read_bytes() == content for r in results)
    assert call_count == 1, "the lock should have prevented a duplicate download"
