"""Phase G: /analyze/femto-bearing-zip (+ /blob) endpoints -> bearing_archive.py.

Only exercises the HTTP wiring and the oversized-body -> analysis_bundle_required
contract; bearing_archive.py's own scientific correctness is covered by
tests/test_bearing_archive.py.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api
from bearing_pdm.bearing_archive import REPO_ROOT

client = TestClient(api.app)

BEARING2_1_DIR = REPO_ROOT / "data/interim/femto/Learning_set/Bearing2_1"
requires_bearing2_1 = pytest.mark.skipif(
    not BEARING2_1_DIR.is_dir(), reason="Bearing2_1 learning-set folder not present locally"
)


def _small_zip(tmp_path: Path) -> Path:
    acc_files = sorted(BEARING2_1_DIR.glob("acc_*.csv"))[:3]
    temp_files = sorted(BEARING2_1_DIR.glob("temp_*.csv"))[:1]
    zip_path = tmp_path / "Bearing2_1.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in [*acc_files, *temp_files]:
            zf.write(f, arcname=f"Bearing2_1/{f.name}")
    return zip_path


@requires_bearing2_1
def test_small_bearing_zip_analyzes_via_direct_upload(tmp_path):
    zip_path = _small_zip(tmp_path)
    with zip_path.open("rb") as f:
        response = client.post(
            "/analyze/femto-bearing-zip", files={"file": ("Bearing2_1.zip", f, "application/zip")}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["bearing_run_id"] == "femto:Bearing2_1"
    assert body["acquisition_count"] == 3


@requires_bearing2_1
def test_oversized_direct_upload_returns_analysis_bundle_required(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "MAX_DIRECT_BEARING_ZIP_BYTES", 1024)
    zip_path = _small_zip(tmp_path)
    with zip_path.open("rb") as f:
        response = client.post(
            "/analyze/femto-bearing-zip", files={"file": ("Bearing2_1.zip", f, "application/zip")}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "analysis_bundle_required"
    assert body["bearing_run_id"] is None


def test_non_zip_upload_is_rejected_cleanly(tmp_path):
    response = client.post(
        "/analyze/femto-bearing-zip",
        files={"file": ("not_a_zip.csv", b"vibration_x\n1.0\n", "text/csv")},
    )
    assert response.status_code == 400
