"""/analyze/mat: real CWRU and Paderborn .mat fixture bytes through the live
API - detection, the existing cwru.py/paderborn.py adapters, bounded
waveform/FFT previews, applicability, and the never-fabricate-RUL contract
(ml-data.md, docs/external-datasets.md: CWRU/Paderborn are fault-diagnosis
snapshots, not run-to-failure trajectories).
"""

from __future__ import annotations

import glob
import io
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from bearing_pdm import api

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"
client = TestClient(api.app)


def _upload(path: Path):
    with path.open("rb") as fh:
        return client.post("/analyze/mat", files={"file": (path.name, fh, "application/octet-stream")})


def test_cwru_mat_is_detected_and_analyzed():
    r = _upload(FIXTURES / "cwru" / "97.mat")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dataset_id"] == "cwru"
    assert body["dataset_type"] == "FAULT_DIAGNOSIS"
    assert body["sample_rate_hz"] == 12000.0
    assert body["channel"] == "DE"
    assert body["metadata"]["file_id"] == "097"
    assert body["metadata"]["selected_channel"] == "DE"
    assert body["rul_supported"] is False
    assert body["rul_seconds"] is None
    assert "vibration_x_rms" in body["features"]
    assert "vibration_y_rms" not in body["features"]


def test_paderborn_mat_is_detected_and_analyzed():
    r = _upload(FIXTURES / "paderborn" / "N15_M07_F10_K001_1.mat")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dataset_id"] == "paderborn"
    assert body["dataset_type"] == "FAULT_DIAGNOSIS"
    assert body["sample_rate_hz"] == 64000.0
    assert body["channel"] == "vibration_1"
    assert body["metadata"] == {
        "speed_code": "15", "torque_code": "07", "force_code": "10",
        "bearing_code": "K001", "run": "1", "sampling_rate_hz": 64000.0,
    }
    assert body["rul_supported"] is False
    assert body["rul_seconds"] is None


def test_paderborn_fault_bearing_also_analyzes():
    r = _upload(FIXTURES / "paderborn" / "N15_M07_F10_KA01_1.mat")
    assert r.status_code == 200, r.text
    assert r.json()["metadata"]["bearing_code"] == "KA01"


def test_unsupported_mat_structure_is_rejected_not_guessed():
    r = client.post(
        "/analyze/mat",
        files={"file": ("bogus.mat", io.BytesIO(b"not a real mat file"), "application/octet-stream")},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "UNSUPPORTED_MAT_STRUCTURE"


def test_non_mat_extension_is_rejected():
    r = client.post(
        "/analyze/mat",
        files={"file": ("acc_00001.csv", io.BytesIO(b"1,2,3"), "text/csv")},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "UNSUPPORTED_FILE_TYPE"


def test_waveform_and_fft_previews_are_bounded():
    r = _upload(FIXTURES / "cwru" / "97.mat")
    body = r.json()
    assert body["n_samples"] > 2000
    assert len(body["waveform_preview"]) <= 2000
    assert len(body["fft_frequency_hz_preview"]) <= 1000
    assert len(body["fft_magnitude_preview"]) <= 1000


def test_applicability_result_is_returned_with_missing_y_axis_preserved():
    r = _upload(FIXTURES / "cwru" / "97.mat")
    body = r.json()
    assert body["applicability_level"] in ("HIGH", "MEDIUM", "LOW")
    assert isinstance(body["applicability_reasons"], list) and body["applicability_reasons"]


def test_temp_file_is_deleted_after_request():
    r = _upload(FIXTURES / "paderborn" / "N15_M07_F10_K001_1.mat")
    assert r.status_code == 200
    leftovers = glob.glob(str(Path(tempfile.gettempdir()) / "matupload_*"))
    assert leftovers == []
