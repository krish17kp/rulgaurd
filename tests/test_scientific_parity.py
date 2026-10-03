"""Scientific release audit (docs/scientific-parity.md) on committed real data.

Tolerances, chosen for float64 roundoff only (never to absorb a method change):
- per-window features vs the offline snapshot: rel=1e-12, abs=1e-12;
- RUL served vs offline: abs=1e-9 s (identical inputs, deterministic trees);
- HI served vs offline: abs=1e-12, stages identical.
deploy_data stores raw samples as float32; the 3-decimal FEMTO text is recovered
exactly from the shortest float32 repr before any comparison (see
recorded_samples), otherwise storage precision (~1e-7 rel) would be measured
instead of the pipeline.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api, artifacts
from bearing_pdm.applicability import HIGH, LOW, MEDIUM, _level, recording_distances
from bearing_pdm.chunked import WindowReport, iter_csv_window_features
from bearing_pdm.health import apply_reference_hi
from bearing_pdm.modeling import predict_tree_baseline
from bearing_pdm.routing import candidates_from_bundle
from bearing_pdm.stages import assign_stages

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy_data"
MODELS = ROOT / "artifacts" / "models"
FIXTURE = ROOT / "data" / "fixtures" / "femto" / "Bearing1_1"
AXES = ("vibration_x", "vibration_y")
WINDOW = api.FEMTO_ACQUISITION_SAMPLES
RATE = api.FEMTO_SAMPLE_RATE_HZ
REQUIRED = ("rul_extra_trees.joblib", "reference_hi_model.joblib", "stage_thresholds.joblib",
            "rul_selected_model.json", api.CROSS_DOMAIN_BUNDLE_NAME)
ARTIFACTS_PRESENT = all((MODELS / name).is_file() for name in REQUIRED)
needs_artifacts = pytest.mark.skipif(not ARTIFACTS_PRESENT,
                                     reason="requires the mounted artifacts/models/ binaries")

client = TestClient(api.app)


def recorded_samples(values) -> np.ndarray:
    return np.asarray(values, dtype=np.float32).astype(str).astype(np.float64)


@pytest.fixture(scope="module")
def snapshot() -> pd.DataFrame:
    return pd.read_parquet(DEPLOY / "feature_snapshot.parquet")


@pytest.fixture(scope="module")
def femto_raw() -> pd.DataFrame:
    raw = pd.read_parquet(DEPLOY / "raw_signal_samples.parquet")
    raw = raw[raw.dataset_id == "femto"].sort_values(["bearing_run_id", "sequence_index"])
    for axis in AXES:
        raw[axis] = raw[axis].map(recorded_samples)
    return raw.reset_index(drop=True)


def _run_frame(group: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({axis: np.concatenate(group[axis].to_numpy()) for axis in AXES})


def _csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, float_format="%.17g").encode()


def test_recorded_sample_recovery_is_exact_on_the_text_fixture():
    text = pd.read_csv(FIXTURE / "acc_00001.csv", header=None)[4].to_numpy()
    np.testing.assert_array_equal(recorded_samples(text.astype(np.float32)), text)


@pytest.mark.parametrize("chunk_rows", [1, 7, 997, WINDOW - 1, WINDOW, WINDOW + 1, 65_536])
def test_chunked_features_on_real_acquisitions_match_offline_snapshot(
        snapshot, femto_raw, chunk_rows, tmp_path):
    reference = snapshot.set_index(["bearing_run_id", "sequence_index"])
    for bearing, group in femto_raw.groupby("bearing_run_id"):
        frame = _run_frame(group)
        path = tmp_path / "run.csv"
        path.write_bytes(_csv(frame))
        for axis in AXES:
            report = WindowReport()
            windows = list(iter_csv_window_features(
                path, vibration_column=axis, window_samples=WINDOW, overlap_samples=0,
                chunk_rows=chunk_rows, sample_rate_hz=RATE, report=report))
            # Every row is read and lands in exactly one window; nothing is dropped.
            assert report.completed and report.rows_read == len(frame)
            assert report.trailing_partial_rows == 0
            assert [(w.row_start, w.row_stop) for w in windows] == [
                (i * WINDOW, (i + 1) * WINDOW) for i in range(len(group))]
            for window, seq in zip(windows, group["sequence_index"], strict=True):
                expected = {k: float(v) for k, v in reference.loc[(bearing, seq)].items()
                            if k in window.features}
                assert expected.keys() == window.features.keys()
                assert window.features == pytest.approx(expected, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("extra_rows", [1, WINDOW - 1])
def test_chunked_reports_every_unwindowed_row(femto_raw, extra_rows, tmp_path):
    group = femto_raw[femto_raw.bearing_run_id == "femto:Bearing2_1"]
    frame = _run_frame(group)
    frame = pd.concat([frame, frame.iloc[:extra_rows]], ignore_index=True)
    path = tmp_path / "run.csv"
    path.write_bytes(_csv(frame))
    report = WindowReport()
    windows = list(iter_csv_window_features(
        path, vibration_column="vibration_x", window_samples=WINDOW, overlap_samples=0,
        chunk_rows=997, sample_rate_hz=RATE, report=report))
    assert len(windows) * WINDOW + report.trailing_partial_rows == report.rows_read == len(frame)
    assert report.trailing_partial_rows == extra_rows
    # The served RUL path refuses the run rather than silently ignoring those rows.
    response = client.post("/analyze/rul", params={
        "dataset_id": "femto", "units": "g", "sampling_rate_hz": RATE,
        "preprocessing_version": api.FEMTO_PREPROCESSING_VERSION,
    }, files={"file": ("run.csv", _csv(frame), "text/csv")})
    assert response.status_code == 422
    assert response.json()["code"] == "INCOMPLETE_RUN"
    assert response.json()["rul_seconds"] is None


@needs_artifacts
def test_analyze_rul_on_real_runs_matches_offline_tree(snapshot, femto_raw):
    tree = joblib.load(MODELS / "rul_extra_trees.joblib")
    for bearing, group in femto_raw.groupby("bearing_run_id"):
        last = snapshot[(snapshot.bearing_run_id == bearing)
                        & (snapshot.sequence_index == group.sequence_index.iloc[-1])]
        offline = float(predict_tree_baseline(last, tree).iloc[0])
        response = client.post("/analyze/rul", params={
            "dataset_id": "femto", "units": "g", "sampling_rate_hz": RATE,
            "preprocessing_version": api.FEMTO_PREPROCESSING_VERSION,
        }, files={"file": ("run.csv", _csv(_run_frame(group)), "text/csv")})
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["rul_seconds"] == pytest.approx(offline, rel=0, abs=1e-9)
        assert body["supporting"]["recordings"] == len(group)


@needs_artifacts
def test_served_artifacts_are_the_manifest_artifacts_and_predict_identically(snapshot):
    manifest = json.loads((MODELS / "manifest.json").read_text())["artifacts"]
    for name, entry in manifest.items():
        digest = hashlib.sha256((MODELS / name).read_bytes()).hexdigest()
        assert digest == entry["sha256"], name
    served = api._load_joblib("rul_extra_trees.joblib")
    assert api._MODEL_VERSIONS["rul_extra_trees.joblib"] == (
        "sha256:" + manifest["rul_extra_trees.joblib"]["sha256"])
    direct = joblib.load(MODELS / "rul_extra_trees.joblib")
    femto = snapshot[snapshot.dataset_id == "femto"]
    np.testing.assert_array_equal(
        served.model.predict(femto[list(served.feature_columns)].fillna(served.median_fill)),
        predict_tree_baseline(femto, direct).to_numpy())


def _manifest(directory: Path, name: str, sha256: str) -> None:
    (directory / "manifest.json").write_text(json.dumps(
        {"artifacts": {name: {"sha256": sha256, "size_bytes": 1, "source_url": None}}}))


def test_local_artifact_that_differs_from_its_manifest_is_refused(tmp_path, monkeypatch):
    """Regression: a stale/wrong local model was served as-is even though the
    manifest beside it records the validated checksum."""
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "MANIFEST_PATH", tmp_path / "manifest.json")
    local = tmp_path / "model.joblib"
    local.write_bytes(b"retrained without updating the manifest")
    _manifest(tmp_path, "model.joblib", hashlib.sha256(b"validated bytes").hexdigest())
    assert artifacts.ensure_artifact("model.joblib") is None

    _manifest(tmp_path, "model.joblib", hashlib.sha256(local.read_bytes()).hexdigest())
    assert artifacts.ensure_artifact("model.joblib") == local


def test_served_model_with_mismatched_checksum_is_unavailable(tmp_path, monkeypatch):
    joblib.dump({"not": "the validated model"}, tmp_path / "rul_extra_trees.joblib")
    _manifest(tmp_path, "rul_extra_trees.joblib", "0" * 64)
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(api, "_MODEL_CACHE", {})
    monkeypatch.setattr(api, "_MODEL_VERSIONS", {})
    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": {"a": 1.0}})
    assert response.status_code == 503
    assert response.json()["code"] == "MODEL_UNAVAILABLE"


@needs_artifacts
def test_served_hi_matches_offline_and_restores_temporal_order(snapshot):
    hi_model = joblib.load(MODELS / "reference_hi_model.joblib")
    thresholds = joblib.load(MODELS / "stage_thresholds.joblib")
    group = (snapshot[snapshot.bearing_run_id == "femto:Bearing3_1"]
             .sort_values("sequence_index").reset_index(drop=True))
    offline = apply_reference_hi(group, hi_model)
    stages = assign_stages(group, offline, thresholds)
    rows = [{**{c: float(r[c]) for c in hi_model.features}, "sequence_index": int(r.sequence_index)}
            for _, r in group.iterrows()]
    rows = [rows[i] for i in np.random.default_rng(0).permutation(len(rows))]
    response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
    assert response.status_code == 200, response.json()
    served = response.json()["rows"]
    assert [r["sequence_index"] for r in served] == group["sequence_index"].tolist()
    np.testing.assert_allclose([r["health_indicator"] for r in served], offline,
                               rtol=0, atol=1e-12)
    assert [r["stage"] for r in served] == stages.tolist()


def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


@needs_artifacts
def test_inference_never_fits_on_uploaded_data(monkeypatch):
    """No scaler/PCA/feature selector/model is fit during a request. The only
    fit allowed is the kNN index over the frozen TRAINING reference rows."""
    from sklearn.base import BaseEstimator

    candidate = next(c for c in candidates_from_bundle(api._load_bundle())
                     if c.name == "raw_seconds")
    reference = candidate.applicability.reference.copy()
    calls = []
    for cls in list(_all_subclasses(BaseEstimator)):
        for attr in ("fit", "partial_fit", "fit_transform", "fit_predict"):
            original = cls.__dict__.get(attr)
            if original is None:
                continue

            def spy(self, *args, _original=original, _name=f"{cls.__name__}.{attr}", **kwargs):
                calls.append((_name, np.asarray(args[0], dtype=float).copy()))
                return _original(self, *args, **kwargs)

            monkeypatch.setattr(cls, attr, spy)
    frame = pd.concat([pd.read_csv(FIXTURE / f"acc_0000{i}.csv", header=None)[[4, 5]]
                       for i in (1, 2)], ignore_index=True)
    frame.columns = list(AXES)
    response = client.post("/analyze/rul", params={
        "dataset_id": "femto", "units": "g", "sampling_rate_hz": RATE,
        "preprocessing_version": api.FEMTO_PREPROCESSING_VERSION,
    }, files={"file": ("run.csv", frame.to_csv(index=False).encode(), "text/csv")})
    assert response.status_code == 200, response.json()
    assert calls, "the applicability kNN index is expected to be built"
    for name, data in calls:
        assert name == "NearestNeighbors.fit"
        np.testing.assert_array_equal(data, reference)
    np.testing.assert_array_equal(candidate.applicability.reference, reference)


def _real_rows_by_level(snapshot) -> dict[str, pd.Series]:
    candidate = next(c for c in candidates_from_bundle(api._load_bundle())
                     if c.name == "raw_seconds").applicability
    femto = snapshot[snapshot.bearing_run_id == "femto:Bearing1_1"].reset_index(drop=True)
    levels = _level(recording_distances(femto, candidate) / candidate.in_domain_distance)
    return {level: femto.iloc[int(np.flatnonzero(levels == level)[-1])]
            for level in (HIGH, MEDIUM, LOW)}


def _features(row: pd.Series) -> dict[str, float]:
    return {k: float(v) for k, v in row.items() if k.startswith(AXES) and np.isfinite(v)}


@needs_artifacts
def test_real_low_applicability_recording_gets_no_rul(snapshot):
    row = _real_rows_by_level(snapshot)[LOW]
    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": _features(row)})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "APPLICABILITY_LOW" and body["compatibility"] == "RETRAIN_REQUIRED"
    assert "rul_seconds" not in body


@needs_artifacts
def test_real_medium_applicability_recording_is_experimental(snapshot):
    row = _real_rows_by_level(snapshot)[MEDIUM]
    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": _features(row)})
    assert response.status_code == 200
    body = response.json()
    assert body["applicability_level"] == MEDIUM
    assert body["compatibility"] == "RETRAIN_REQUIRED"
    assert "experimental" in body["applicability_reasons"][0]


@needs_artifacts
def test_real_high_applicability_recording_is_fully_supported(snapshot):
    row = _real_rows_by_level(snapshot)[HIGH]
    response = client.post("/predict/rul", json={"dataset_id": "femto", "features": _features(row)})
    assert response.status_code == 200
    assert response.json()["applicability_level"] == HIGH
    assert response.json()["compatibility"] == "FULLY_SUPPORTED"


def _acquisition_lines() -> list[str]:
    return (FIXTURE / "acc_00001.csv").read_text().splitlines()


def _post_acquisition(lines: list[str]):
    return client.post("/predict/rul/femto-acquisition",
                       files={"file": ("acc.csv", ("\n".join(lines) + "\n").encode(), "text/csv")})


def test_reordered_acquisition_rows_fail_closed(monkeypatch):
    """Regression: shuffled rows keep every time-domain feature but scramble
    the spectrum, and previously still received a FULLY_SUPPORTED RUL."""
    monkeypatch.setattr(api, "_predict_rul_from_features",
                        lambda *_: pytest.fail("RUL must not run"))
    lines = _acquisition_lines()
    lines = [lines[i] for i in np.random.default_rng(0).permutation(len(lines))]
    response = _post_acquisition(lines)
    assert response.status_code == 422
    assert response.json()["code"] == "SAMPLES_OUT_OF_ORDER"
    assert response.json()["compatibility"] == "INVALID_INPUT"


def test_acquisition_with_missing_timestamp_fails_closed(monkeypatch):
    monkeypatch.setattr(api, "_predict_rul_from_features",
                        lambda *_: pytest.fail("RUL must not run"))
    lines = _acquisition_lines()
    lines[100] = "," + lines[100].split(",", 1)[1]
    response = _post_acquisition(lines)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_TIMESTAMPS"


@needs_artifacts
def test_in_order_acquisition_across_midnight_is_accepted():
    lines = _acquisition_lines()
    shifted = []
    for i, line in enumerate(lines):
        cells = line.split(",")
        # Same samples, clock moved so the acquisition crosses 23:59:59 -> 00:00:00.
        cells[:4] = (["23", "59", "59"] if i < 1280 else ["0", "0", "0"]) + [str(39 * (i % 1280))]
        shifted.append(",".join(cells))
    reference = _post_acquisition(lines)
    response = _post_acquisition(shifted)
    assert reference.status_code == response.status_code == 200, response.json()
    assert response.json()["rul_seconds"] == reference.json()["rul_seconds"]
