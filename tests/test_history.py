"""History persistence, retention, concurrency and API privacy contracts."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bearing_pdm import api, artifacts
from bearing_pdm.history import (
    InMemoryHistoryStore,
    SQLiteHistoryStore,
    configured_history_store,
)


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_round_trip_bound_and_snapshot(tmp_path, backend):
    store = (InMemoryHistoryStore(2) if backend == "memory"
             else SQLiteHistoryStore(str(tmp_path / "history.db"), 2))
    for i in range(3):
        record = {"id": str(i), "result": {"value": i}}
        store.append(record)
        record["result"]["value"] = -1
    assert store.recent() == [
        {"id": "2", "result": {"value": 2}}, {"id": "1", "result": {"value": 1}},
    ]
    store.recent()[0]["result"]["value"] = -2
    assert store.recent()[0]["result"]["value"] == 2


def test_append_trims_rows_without_reopen(tmp_path):
    # recent() applies LIMIT itself, so only a raw row count proves append() trims.
    path = str(tmp_path / "history.db")
    store = SQLiteHistoryStore(path, 3)
    for i in range(10):
        store.append({"id": str(i)})
        with closing(sqlite3.connect(path)) as conn:
            count = conn.execute("SELECT count(*) FROM prediction_history").fetchone()[0]
        assert count == min(i + 1, 3)
    assert [r["id"] for r in store.recent()] == ["9", "8", "7"]


def test_restart_and_concurrent_writes(tmp_path):
    path = str(tmp_path / "history.db")
    stores = [SQLiteHistoryStore(path, 40) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: stores[i % 4].append({"id": str(i)}), range(100)))
    restarted = SQLiteHistoryStore(path, 40)
    assert len(restarted.recent()) == 40
    assert len({r["id"] for r in restarted.recent()}) == 40
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("SELECT count(*) FROM prediction_history").fetchone()[0] == 40
    assert len(SQLiteHistoryStore(path, 5).recent()) == 5


def test_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv("RULGUARD_HISTORY_DB", raising=False)
    monkeypatch.delenv("RULGUARD_HISTORY_LIMIT", raising=False)
    assert isinstance(configured_history_store(), InMemoryHistoryStore)
    monkeypatch.setenv("RULGUARD_HISTORY_DB", str(tmp_path / "history.db"))
    monkeypatch.setenv("RULGUARD_HISTORY_LIMIT", "3")
    assert configured_history_store().limit == 3
    monkeypatch.setenv("RULGUARD_HISTORY_LIMIT", "0")
    with pytest.raises(ValueError):
        configured_history_store()


def test_api_success_failure_and_no_input_persistence(monkeypatch, tmp_path):
    path = tmp_path / "history.db"
    monkeypatch.setattr(api, "_history_store", SQLiteHistoryStore(str(path)))
    model = SimpleNamespace(feature_columns=["x", "y"], median_fill={"y": 0},
                            model=SimpleNamespace(predict=lambda x: [3600]))
    # No cross-domain bundle: the synthetic two-feature model has no fitted
    # applicability reference, so the gate degrades honestly (not assessed).
    # Seed both names _load_bundle tries (it prefers APPLICABILITY_BUNDLE_NAME,
    # falling back to CROSS_DOMAIN_BUNDLE_NAME) so neither hits the real
    # on-disk artifact.
    monkeypatch.setattr(api, "_MODEL_CACHE", {"rul_extra_trees.joblib": model,
                                              api.APPLICABILITY_BUNDLE_NAME: None,
                                              api.CROSS_DOMAIN_BUNDLE_NAME: None})
    monkeypatch.setattr(api, "_MODEL_VERSIONS", {"rul_extra_trees.joblib": "sha256:test"})
    with TestClient(api.app) as client:
        payload = {"dataset_id": "femto", "features": {"x": 987654.321}}
        assert client.post("/predict/rul", json=payload).status_code == 200
        payload["dataset_id"] = "private-dataset-name"
        payload["features"]["private-channel-name"] = 123456.789
        assert client.post("/predict/rul", json=payload).status_code == 422
        records = client.get("/predictions/history").json()["predictions"]
    failed, success = records
    assert failed["status"] == "failed"
    assert failed["result"] is None
    assert failed["compatibility_state"] == "UNSUPPORTED"
    assert failed["error_code"] == "UNSUPPORTED_DATASET"
    assert success["status"] == "succeeded"
    assert success["result"]["rul_hours"] == 1
    assert success["model_version"] == "sha256:test"
    assert success["feature_schema_version"].startswith("sha256:")
    assert success["warnings"] == ["MISSING_FEATURES_MEDIAN_FILLED", "APPLICABILITY_NOT_ASSESSED"]
    # Production-policy fix (M2, release review): compatibility must not be FULLY_SUPPORTED
    # when applicability was never assessed - downgraded to the same RETRAIN_REQUIRED
    # "experimental" state MEDIUM applicability uses, not left at the FULLY_SUPPORTED default.
    assert success["compatibility_state"] == "RETRAIN_REQUIRED"
    assert success["id"] != failed["id"]
    assert datetime.fromisoformat(success["timestamp"]).tzinfo is not None
    assert SQLiteHistoryStore(str(path)).recent() == records
    serialized = json.dumps(records)
    for secret in ("987654.321", "123456.789", "private-channel-name", "private-dataset-name"):
        assert secret not in serialized
        for file in tmp_path.glob("history.db*"):
            assert secret.encode() not in file.read_bytes()


def test_history_failure_is_explicit(monkeypatch):
    class BrokenStore:
        def append(self, record):
            raise OSError("private storage path")

        def recent(self):
            raise OSError("private storage path")

    monkeypatch.setattr(api, "_history_store", BrokenStore())
    with TestClient(api.app) as client:
        for response in (
            client.post("/predict/rul", json={"dataset_id": "other", "features": {}}),
            client.get("/predictions/history"),
        ):
            assert response.status_code == 503
            assert response.json()["code"] == "HISTORY_UNAVAILABLE"
            assert "private storage path" not in response.text


def test_fingerprint_order_and_artifact_version(monkeypatch, tmp_path):
    import hashlib

    import joblib

    assert api._fingerprint({"b": 2, "a": 1}) == api._fingerprint({"a": 1, "b": 2})
    assert api._fingerprint({"a": 1}) != api._fingerprint({"a": 2})
    path = tmp_path / "model.joblib"
    joblib.dump({"test": True}, path)
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(api, "_MODEL_CACHE", {})
    monkeypatch.setattr(api, "_MODEL_VERSIONS", {})
    assert api._load_joblib("model.joblib") == {"test": True}
    assert api._MODEL_VERSIONS["model.joblib"] == (
        "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    )


def test_hi_summary_tracks_both_artifacts(monkeypatch):
    store = InMemoryHistoryStore()
    monkeypatch.setattr(api, "_history_store", store)
    monkeypatch.setattr(api, "_MODEL_CACHE", {
        "reference_hi_model.joblib": SimpleNamespace(features=["x"]),
    })
    versions = {"reference_hi_model.joblib": "reference", "stage_thresholds.joblib": "thresholds"}
    monkeypatch.setattr(api, "_MODEL_VERSIONS", versions)

    @api._track_prediction("predict_hi", "reference_hi_model.joblib")
    def predict(request):
        return SimpleNamespace(rows=[SimpleNamespace(health_indicator=0.5, stage="test")])

    request = api.HiRequest(dataset_id="femto", rows=[{"x": 123.456}])
    predict(request)
    first = store.recent()[0]
    versions["stage_thresholds.joblib"] = "changed"
    predict(request)
    assert store.recent()[0]["model_version"] != first["model_version"]
    assert first["result"] == {"latest_hi": 0.5, "latest_stage": "test"}
    assert first["warnings"] == ["HI_STAGE_IS_SEVERITY_NOT_FAULT_DIAGNOSIS"]
    assert "123.456" not in json.dumps(store.recent())
