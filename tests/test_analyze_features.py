"""POST /analyze/features: staged upload -> detection -> validation -> preprocessing
-> feature extraction, on real fixture recordings and fail-closed negative cases."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api
from bearing_pdm.adapters import ADAPTERS
from bearing_pdm.chunked import scan_csv_column
from bearing_pdm.features import frequency_domain_features, time_domain_features

client = TestClient(api.app)
FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"
FEMTO_ACC = FIXTURES / "femto" / "Bearing1_1" / "acc_00001.csv"
COLLEGE = FIXTURES / "college" / "LogFile_2022-06-20-17-00-31_head5000.csv"
FEMTO_RATE = ADAPTERS["femto"].sampling_rate_hz
COLLEGE_RATE = ADAPTERS["college"].sampling_rate_hz


def _headered(path: Path, columns: dict[int, str]) -> bytes:
    """The real fixture's samples, unchanged, under a header naming the channels
    as the adapter documents them (the fixtures themselves are headerless)."""
    raw = pd.read_csv(path, header=None)
    return raw[list(columns)].rename(columns=columns).to_csv(index=False).encode()


def _post(content: bytes, name: str = "upload.csv", **params):
    return client.post("/analyze/features", params=params,
                       files={"file": (name, content, "text/csv")})


def _stages(body: dict) -> dict[str, str]:
    return {s["name"]: s["status"] for s in body["stages"]}


def test_femto_fixture_features_match_direct_computation():
    content = _headered(FEMTO_ACC, {4: "vibration_x", 5: "vibration_y"})
    response = _post(content, channel="vibration_x", sampling_rate_hz=FEMTO_RATE,
                     window_samples=512, overlap_samples=256)
    assert response.status_code == 200, response.json()
    body = response.json()
    assert [s["name"] for s in body["stages"]] == list(api.ANALYZE_STAGES)
    assert set(_stages(body).values()) == {"ok"}
    assert body["health_indicator_produced"] is False and body["prediction_produced"] is False
    assert body["sampling"] == {**body["sampling"], "rate_hz": FEMTO_RATE, "source": "user"}
    assert body["signal"]["rows"] == 2560
    assert body["windows_total"] == (2560 - 512) // 256 + 1 == body["windows_returned"]
    assert body["truncated"] is False and body["truncation_note"] is None

    x = pd.read_csv(FEMTO_ACC, header=None)[4].to_numpy(dtype=float)
    last = body["windows"][-1]
    segment = x[last["row_start"]:last["row_stop"]]
    expected = time_domain_features(segment, "vibration_x")
    expected.update(frequency_domain_features(segment, FEMTO_RATE, "vibration_x"))
    assert body["feature_names"] == list(expected)
    np.testing.assert_allclose([last["features"][k] for k in expected], list(expected.values()))


def test_canonical_channel_name_resolves_header_alias():
    content = _headered(FEMTO_ACC, {4: "horizontal_acceleration"})
    body = _post(content, channel="vibration_x", sampling_rate_hz=FEMTO_RATE).json()
    assert body["channel"] == {"column": "horizontal_acceleration", "canonical": "vibration_x"}
    assert body["windows_total"] == 1  # default window is the 2560-sample FEMTO acquisition


def test_college_fixture_truncates_returned_windows(monkeypatch):
    monkeypatch.setattr(api, "MAX_RETURNED_WINDOWS", 3)
    content = _headered(COLLEGE, {0: "vibration_x", 1: "vibration_y"})
    response = _post(content, channel="vibration_y", sampling_rate_hz=COLLEGE_RATE,
                     window_samples=1024)
    body = response.json()
    assert response.status_code == 200, body
    assert body["windows_total"] == 5000 // 1024
    assert body["windows_returned"] == 3 and len(body["windows"]) == 3
    assert body["truncated"] is True and "3 of 4" in body["truncation_note"]
    assert "capped" in next(s for s in body["stages"] if s["name"] == "feature_extraction")["detail"]


def test_rate_derived_from_regular_timestamps():
    t = np.arange(64) / 1000.0
    content = pd.DataFrame({"time_s": t, "vibration_x": np.sin(t * 700)}).to_csv(index=False).encode()
    body = _post(content, channel="vibration_x", window_samples=32).json()
    assert body["sampling"]["source"] == "timestamps"
    assert body["sampling"]["rate_hz"] == pytest.approx(1000.0)


def _assert_failed(response, status, code, failed_stage):
    body = response.json()
    assert response.status_code == status, body
    assert body["code"] == code and body["failed_stage"] == failed_stage
    states = _stages(body)
    assert states[failed_stage] == "failed"
    order = list(api.ANALYZE_STAGES)
    position = order.index(failed_stage)
    assert all(states[name] == "ok" for name in order[:position])
    assert all(states[name] == "skipped" for name in order[position + 1:])
    assert "windows" not in body
    return body


def test_extreme_finite_values_fail_extraction_not_500():
    """Regression (same defect class HEAD fixed on /predict/rul/femto-acquisition):
    finite samples large enough that features.py's std**4 overflows raised an
    unhandled OverflowError - a 500 instead of a staged 422."""
    rng = np.random.default_rng(0)
    content = pd.DataFrame({"vibration_x": rng.normal(size=64) * 1e80}).to_csv(index=False).encode()
    response = TestClient(api.app, raise_server_exceptions=False).post(
        "/analyze/features", params={"channel": "vibration_x", "sampling_rate_hz": 1000,
                                     "window_samples": 32},
        files={"file": ("big.csv", content, "text/csv")})
    _assert_failed(response, 422, "FEATURE_EXTRACTION_FAILED", "feature_extraction")


def test_missing_sampling_rate_fails_validation():
    content = _headered(FEMTO_ACC, {4: "vibration_x"})
    _assert_failed(_post(content, channel="vibration_x"), 422, "SAMPLING_RATE_REQUIRED",
                   "validation")


def test_too_short_fails_validation():
    content = _headered(FEMTO_ACC, {4: "vibration_x"})
    body = _assert_failed(_post(content, channel="vibration_x", sampling_rate_hz=FEMTO_RATE,
                                window_samples=4096), 422, "INSUFFICIENT_SAMPLES", "validation")
    assert "2560 samples" in body["detail"]


def test_non_numeric_after_profiled_head_fails_validation():
    content = _headered(FEMTO_ACC, {4: "vibration_x"})
    # Rows past profile_file's 5000-row sample are only seen by the whole-file scan.
    content += content.split(b"\n", 1)[1] * 2 + b"abc\n"
    body = _assert_failed(_post(content, channel="vibration_x", sampling_rate_hz=FEMTO_RATE),
                          422, "NON_NUMERIC_SIGNAL", "validation")
    assert body["validation_errors"] == [{"code": "NON_NUMERIC_SIGNAL", "reason": body["detail"]}]
    assert "abc" not in body["detail"]  # counts only, never cell values


def test_constant_channel_fails_validation():
    content = b"vibration_x,vibration_y\n" + b"1.0,0.5\n" * 20 + b"1.0,0.7\n" * 20
    _assert_failed(_post(content, channel="vibration_x", sampling_rate_hz=100, window_samples=8),
                   422, "CONSTANT_SIGNAL", "validation")


@pytest.mark.parametrize("content, code", [
    (b"vibration_x\n1\n2\ninf\n3\n", "NON_FINITE_SIGNAL"),
    (b"vibration_x\n1\n\n\n\n2\n", "EXCESSIVE_MISSING"),
    (b"timestamp,vibration_x\n1,1\n3,2\n2,3\n4,1\n", "SAMPLES_OUT_OF_ORDER"),
    (b"time_s,vibration_x\n0,1\n0.1,2\n0.3,3\n0.4,1\n", "TIMESTAMPS_IRREGULAR"),
])
def test_signal_quality_and_ordering_fail_validation(content, code):
    _assert_failed(_post(content, channel="vibration_x", sampling_rate_hz=10, window_samples=2),
                   422, code, "validation")


def test_rate_conflicting_with_timestamps_fails_validation():
    content = b"time_s,vibration_x\n0,1\n0.1,2\n0.2,3\n0.3,1\n"
    _assert_failed(_post(content, channel="vibration_x", sampling_rate_hz=20, window_samples=2),
                   422, "SAMPLING_RATE_CONFLICT", "validation")


def test_overlap_not_below_window_fails_validation():
    content = _headered(FEMTO_ACC, {4: "vibration_x"})
    _assert_failed(_post(content, channel="vibration_x", sampling_rate_hz=FEMTO_RATE,
                         window_samples=8, overlap_samples=8), 422, "INVALID_WINDOW", "validation")


def test_excessive_compute_is_rejected_before_extraction(monkeypatch):
    import bearing_pdm.chunked as chunked

    monkeypatch.setattr(chunked, "iter_csv_window_features",
                        lambda *a, **k: pytest.fail("extractor must not run"))
    window = api.MAX_WINDOW_SAMPLES
    # A ~2MB upload whose maximal overlap would featurise 17 x 1M samples.
    content = b"vibration_x\n" + b"1\n2\n" * ((window + 16) // 2)
    body = _assert_failed(_post(content, channel="vibration_x", sampling_rate_hz=FEMTO_RATE,
                                window_samples=window, overlap_samples=window - 1),
                          422, "COMPUTE_LIMIT_EXCEEDED", "preprocessing")
    assert str(api.MAX_COMPUTED_SAMPLES) in body["detail"]
    assert 17 * window > api.MAX_COMPUTED_SAMPLES


def test_user_rate_timestamp_check_reports_user_rate():
    content = _headered(FEMTO_ACC, {4: "vibration_x"})
    body = _post(content, channel="vibration_x", sampling_rate_hz=FEMTO_RATE).json()
    check = body["sampling"]["timestamp_check"]
    assert body["sampling"]["source"] == "user"
    assert "no justified sampling rate" not in check
    assert "User-supplied sampling_rate_hz" in check and f"{FEMTO_RATE:g}" in check

    t = np.arange(64) / 1000.0
    content = pd.DataFrame({"time_s": t, "vibration_x": np.sin(t * 700)}).to_csv(index=False).encode()
    body = _post(content, channel="vibration_x", sampling_rate_hz=1000, window_samples=32).json()
    assert "agrees with the file's timestamps" in body["sampling"]["timestamp_check"]


def test_headerless_real_fixture_fails_detection():
    body = _assert_failed(_post(FEMTO_ACC.read_bytes(), channel="vibration_x",
                                sampling_rate_hz=FEMTO_RATE), 422, "ADAPTER_REQUIRED",
                          "dataset_detection")
    assert body["compatibility"] == "ADAPTER_REQUIRED"


@pytest.mark.parametrize("content, channel, code", [
    (b"vibration_x,temperature_bearing\n1,20\n2,21\n", "vibration_z", "CHANNEL_NOT_FOUND"),
    (b"vibration_x,temperature_bearing\n1,20\n2,21\n", "temperature_bearing",
     "CHANNEL_NOT_VIBRATION"),
    (b"acc_x,vib_x\n1,2\n2,1\n", "vibration_x", "CHANNEL_AMBIGUOUS"),
    (b"foo,bar\n1,2\n", "foo", "NO_VIBRATION_CHANNEL"),
    (b"vibration_x;vibration_y\n1;2\n2;1\n", "vibration_x", "UNSUPPORTED_DELIMITER"),
])
def test_channel_and_format_fail_detection(content, channel, code):
    _assert_failed(_post(content, channel=channel, sampling_rate_hz=10, window_samples=2),
                   422, code, "dataset_detection")


def test_upload_failures_are_attributed_to_upload(monkeypatch):
    _assert_failed(_post(b"", channel="vibration_x", sampling_rate_hz=10), 422, "EMPTY_UPLOAD",
                   "upload")
    _assert_failed(_post(b"PK\x03\x04junk", channel="vibration_x", sampling_rate_hz=10), 415,
                   "UNSUPPORTED_FILE_TYPE", "upload")
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 10)
    _assert_failed(_post(b"vibration_x\n" + b"1.0\n" * 100, channel="vibration_x",
                         sampling_rate_hz=10), 413, "UPLOAD_TOO_LARGE", "upload")


def test_channel_is_required():
    response = _post(b"vibration_x\n1\n2\n", sampling_rate_hz=10)
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"


def test_temp_file_removed_and_failed_stage_logged(monkeypatch, caplog):
    created = []
    original = api.tempfile.NamedTemporaryFile

    def tracking(*args, **kwargs):
        handle = original(*args, **kwargs)
        created.append(Path(handle.name))
        return handle

    monkeypatch.setattr(api.tempfile, "NamedTemporaryFile", tracking)
    content = _headered(FEMTO_ACC, {4: "vibration_x"})
    with caplog.at_level("INFO", logger="bearing_pdm.api"):
        assert _post(content, channel="vibration_x", sampling_rate_hz=FEMTO_RATE).status_code == 200
        assert _post(content, channel="vibration_x").status_code == 422
    assert len(created) == 2 and not any(p.exists() for p in created)
    records = [r for r in caplog.records if getattr(r, "stage", None) == "analyze_features"]
    assert records[-1].pipeline_stage == "validation"
    assert records[-1].code == "SAMPLING_RATE_REQUIRED"
    assert "0.552" not in " ".join(r.getMessage() for r in records)  # no sensor values


def test_scan_counts_match_reader(tmp_path):
    path = tmp_path / "s.csv"
    path.write_text("t,v\n1,1\n2,\n2,x\n4,inf\n5,2\n")
    scan = scan_csv_column(path, column="v", chunk_rows=2, order_column="t")
    assert (scan.rows, scan.missing, scan.non_numeric, scan.infinite) == (5, 1, 1, 1)
    assert (scan.finite_min, scan.finite_max) == (1.0, 2.0)
    assert scan.order_column_rows_out_of_order == 1
