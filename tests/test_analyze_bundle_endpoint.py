"""Phase 5 (nightshift continuation): /analyze/bundle - load a portable
`.rulguard.zip` Analysis Bundle for display. Real build_bundle()-produced
archives through the real endpoint, plus the required rejection cases
(corrupt checksum, missing manifest, unsupported schema version, malformed
ZIP) - never a raw traceback for any of them.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient

from bearing_pdm import api
from bearing_pdm.analysis_bundle import build_bundle

client = TestClient(api.app)


def _post(data: bytes):
    return client.post("/analyze/bundle", files={"file": ("bundle.rulguard.zip", data, "application/zip")})


def test_femto_shaped_bundle_is_loaded_and_classified(tmp_path):
    payload = {
        "bearing_run_id": "femto:Bearing2_1",
        "acquisition_count": 3,
        "sample_rate_hz": 25600.0,
        "sequence_index": [0, 1, 2],
        "actual_rul_seconds": [20.0, 10.0, 0.0],
    }
    bundle_path = build_bundle("femto:Bearing2_1", payload, tmp_path / "femto.rulguard.zip")
    resp = _post(bundle_path.read_bytes())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["kind"] == "femto"
    assert body["dataset_id"] == "femto:Bearing2_1"
    assert body["payload"]["acquisition_count"] == 3


def test_college_shaped_bundle_is_loaded_and_classified(tmp_path):
    payload = {
        "college:nsk6205": {
            "dataset_id": "college",
            "n_acquisitions": 2,
            "actual_rul_seconds": [10.0, 0.0],
        }
    }
    bundle_path = build_bundle("college", payload, tmp_path / "college.rulguard.zip")
    resp = _post(bundle_path.read_bytes())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["kind"] == "college"
    assert body["dataset_id"] == "college"


def test_corrupt_checksum_is_rejected_with_400_not_a_traceback(tmp_path):
    bundle_path = build_bundle("femto:Bearing2_1", {"bearing_run_id": "femto:Bearing2_1"},
                                tmp_path / "ok.rulguard.zip")
    buf = BytesIO(bundle_path.read_bytes())
    with zipfile.ZipFile(buf) as zf:
        manifest = zf.read("manifest.json")
        checksums = zf.read("checksums.json")
    tampered = BytesIO()
    with zipfile.ZipFile(tampered, "w") as zf:
        zf.writestr("manifest.json", manifest)
        zf.writestr("dataset.json", b'{"bearing_run_id": "tampered"}')
        zf.writestr("checksums.json", checksums)

    resp = _post(tampered.getvalue())
    assert resp.status_code == 400
    assert "checksum" in resp.json()["detail"]


def test_missing_manifest_member_is_rejected(tmp_path):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dataset.json", b"{}")
        zf.writestr("checksums.json", b"{}")
    resp = _post(buf.getvalue())
    assert resp.status_code == 400
    assert "missing members" in resp.json()["detail"]


def test_unsupported_schema_version_is_rejected(tmp_path):
    dataset_bytes = b'{"a": 1}'
    import hashlib
    dataset_sha = hashlib.sha256(dataset_bytes).hexdigest()
    manifest = {"schema_version": "999.0", "format": "rulguard.zip",
                "dataset_id": "x", "dataset_sha256": dataset_sha}
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
    checksums = {"dataset.json": dataset_sha,
                 "manifest.json": hashlib.sha256(manifest_bytes).hexdigest()}
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("dataset.json", dataset_bytes)
        zf.writestr("checksums.json", json.dumps(checksums, sort_keys=True).encode())
    resp = _post(buf.getvalue())
    assert resp.status_code == 400
    assert "schema_version" in resp.json()["detail"]


def test_malformed_zip_is_rejected_not_a_500():
    resp = _post(b"this is not a zip file at all")
    assert resp.status_code == 400
    assert "not a valid ZIP" in resp.json()["detail"]
