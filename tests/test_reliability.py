"""Goal 21: reliability information on /predict/rul, only from defensible sources.

Synthetic models/bundles make every branch deterministic; one test also runs
against the real cached artifacts when they are mounted."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import ExtraTreesRegressor

from bearing_pdm import api, artifacts, reliability
from bearing_pdm.applicability import LOW, MEDIUM, ApplicabilityModel
from bearing_pdm.modeling import TreeBaseline
from bearing_pdm.uncertainty import ConformalCalibrator, conformal_interval, tree_predictions

COLUMNS = ("a", "b")
FORBIDDEN_KEY_PARTS = ("confidence", "probability", "percent", "pct")


def _served(seed: int = 0) -> TreeBaseline:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(200, 2))
    y = 10_000 + 3_000 * x[:, 0] + rng.normal(scale=500, size=200)
    forest = ExtraTreesRegressor(n_estimators=20, random_state=seed).fit(x, y)
    return TreeBaseline(feature_columns=COLUMNS, model=forest, median_fill={"a": 0.0, "b": 0.0})


def _bundle(model: TreeBaseline, train: str = "femto") -> dict:
    app = ApplicabilityModel(
        feature_columns=COLUMNS, center=np.zeros(2), scale=np.ones(2),
        reference=np.random.default_rng(1).normal(size=(100, 2)), k=5,
        in_domain_distance=0.5, in_domain_distances={"b1": 0.4, "b2": 0.5},
        sampling_rates_hz=(), rpm_range=None, load_range=None,
    )
    cal = ConformalCalibrator(alpha=0.1, quantile=2.0, beta=10.0, n_calibration_rows=600,
                              n_calibration_bearings=6)
    return {"raw_seconds": {"model": model, "calibrators": {"conformal": cal},
                            "applicability": app, "train": train}}


def _metrics() -> dict:
    per_bearing = [
        {"model": "extra_trees", "held_out_bearing": "Bearing1_1", "mae_seconds": 4000.0, "n": 10},
        {"model": "extra_trees", "held_out_bearing": "Bearing1_2", "mae_seconds": 9000.0, "n": 5},
        {"model": "naive", "held_out_bearing": "Bearing1_1", "mae_seconds": 1.0, "n": 10},
    ]
    overall = {"mae_seconds": 5666.7, "rmse_seconds": 7000.0, "median_abs_error_seconds": 5000.0,
               "mean_signed_error_seconds": 1200.0, "n": 15, "n_overestimates": 9,
               "n_underestimates": 6, "overestimate_rate": 0.6}
    return {"femto_lobo": per_bearing,
            "femto_lobo_overall_by_model": {"extra_trees": overall, "naive": overall}}


def _keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _keys(inner)


def _assert_no_confidence_fields(block: dict) -> None:
    bad = [k for k in _keys(block) if any(p in k.lower() for p in FORBIDDEN_KEY_PARTS)]
    assert bad == []


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """API pointed at an empty artifact/metrics dir with a synthetic served model."""
    model = _served()
    monkeypatch.setattr(artifacts, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "MANIFEST_PATH", tmp_path / "manifest.json")  # no real source_url to fall back to - genuinely unavailable, not just locally missing
    monkeypatch.setattr(api, "METRICS_DIR", tmp_path)
    monkeypatch.setattr(api, "_MODEL_CACHE", {"rul_extra_trees.joblib": model})
    return tmp_path, model


def _use_bundle(bundle: dict) -> None:
    # The bundle is loaded through the same verified loader/cache as every model.
    api._MODEL_CACHE[api.CROSS_DOMAIN_BUNDLE_NAME] = bundle


def _predict(features: dict) -> dict:
    response = TestClient(api.app).post("/predict/rul",
                                        json={"dataset_id": "femto", "features": features})
    assert response.status_code == 200
    return response.json()


def test_missing_artifacts_give_null_with_reason_and_keep_old_fields(isolated):
    body = _predict({"a": 0.1, "b": -0.2})
    assert set(body) == {"model_name", "rul_seconds", "rul_hours", "features_used",
                         "features_missing", "compatibility", "applicability_level",
                         "applicability_shift_ratio", "applicability_reasons", "reliability"}
    assert body["rul_hours"] == pytest.approx(body["rul_seconds"] / 3600.0)
    rel = body["reliability"]
    assert rel["held_out_error"]["available"] is False
    assert "rul_evaluation.json" in rel["held_out_error"]["reason"]
    assert "mae_seconds" not in rel["held_out_error"]
    assert rel["interval"] is None and "cross_domain_bundle.joblib" in rel["interval_reason"]
    assert rel["applicability"] is None and rel["applicability_reason"]
    # Tree disagreement is a computation on the served model: available, labelled diagnostic.
    trees = rel["tree_disagreement"]
    assert trees["available"] is True and trees["kind"] == "diagnostic_not_calibrated"
    assert trees["unit"] == "seconds" and trees["n_trees"] == 20
    _assert_no_confidence_fields(body)


def test_full_block_traces_to_file_and_cached_calibrator(isolated):
    tmp_path, model = isolated
    (tmp_path / "rul_evaluation.json").write_text(json.dumps(_metrics()))
    _use_bundle(_bundle(model))
    body = _predict({"a": 0.1, "b": -0.2})
    rel = body["reliability"]
    # One applicability verdict per response: the gate and the block agree.
    assert body["applicability_level"] == rel["applicability"]["level"] == "HIGH"

    held = rel["held_out_error"]
    assert held["available"] is True and held["unit"] == "seconds"
    assert held["mae_seconds"] == 5666.7 and held["n_held_out_rows"] == 15
    assert held["n_held_out_bearings"] == 2  # the naive rows are not mixed in
    assert (held["per_bearing_mae_seconds_min"], held["per_bearing_mae_seconds_max"]) == (4000, 9000)

    x = pd.DataFrame([{"a": 0.1, "b": -0.2}])
    sigma = float(tree_predictions(model.model, x)[:, 0].std())
    assert rel["tree_disagreement"]["std_seconds"] == pytest.approx(sigma)

    assert rel["applicability"]["level"] != LOW and rel["applicability_reason"] is None
    conf = rel["interval"]
    lo, hi = conformal_interval(np.array([body["rul_seconds"]]), np.array([sigma]),
                                _bundle(model)["raw_seconds"]["calibrators"]["conformal"],
                                lower_bound=0.0)
    assert (conf["lower_seconds"], conf["upper_seconds"]) == pytest.approx((lo[0], hi[0]))
    assert conf["lower_seconds"] <= body["rul_seconds"] <= conf["upper_seconds"]
    assert conf["unit"] == "seconds"
    assert conf["lower_hours"] == pytest.approx(conf["lower_seconds"] / 3600.0)
    assert conf["upper_hours"] == pytest.approx(conf["upper_seconds"] / 3600.0)
    assert conf["target_miscoverage_alpha"] == 0.1 and conf["n_calibration_bearings"] == 6
    _assert_no_confidence_fields(body)


def test_out_of_distribution_row_is_suppressed_not_served(isolated):
    # LOW applicability suppresses the prediction itself (routing.py's
    # RUL_SUPPRESSED): no number, so no interval either.
    _, model = isolated
    _use_bundle(_bundle(model))
    response = TestClient(api.app).post(
        "/predict/rul", json={"dataset_id": "femto", "features": {"a": 40.0, "b": -40.0}})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "APPLICABILITY_LOW" and body["compatibility"] == "RETRAIN_REQUIRED"
    assert "rul_seconds" not in body and "reliability" not in body


def test_out_of_distribution_row_withholds_interval(isolated):
    _, model = isolated
    bundle = _bundle(model)
    x = pd.DataFrame([{"a": 40.0, "b": -40.0}])
    app, _ = reliability.applicability(bundle, list(COLUMNS), {"a": 40.0, "b": -40.0},
                                       single_recording=True)
    assert app["level"] == LOW
    conf, reason = reliability.interval(bundle, model, x, float(model.model.predict(x)[0]),
                                        1.0, app)
    assert conf is None and "LOW" in reason


def test_missing_feature_is_reported_as_unavailable_not_median(isolated):
    _, model = isolated
    _use_bundle(_bundle(model))
    body = _predict({"a": 0.1})
    assert body["features_missing"] == ["b"]
    assert body["reliability"]["applicability"]["missing_features"] == ["b"]
    # Single-recording semantics (applicability.assess): half of one row's
    # features present caps at MEDIUM - served as experimental, never with an
    # interval, and the same level the response's own gate reports.
    assert body["reliability"]["applicability"]["level"] == MEDIUM
    assert body["applicability_level"] == MEDIUM
    assert body["compatibility"] == "RETRAIN_REQUIRED"
    assert body["reliability"]["interval"] is None
    assert "MEDIUM" in body["reliability"]["interval_reason"]


def test_calibrator_of_a_different_model_is_not_applied(isolated):
    _use_bundle(_bundle(_served(seed=7)))
    rel = _predict({"a": 0.1, "b": -0.2})["reliability"]
    assert rel["interval"] is None and "different model" in rel["interval_reason"]


def test_bundle_not_fit_on_femto_is_not_used(isolated):
    _, model = isolated
    _use_bundle(_bundle(model, train="college"))
    rel = _predict({"a": 0.1, "b": -0.2})["reliability"]
    assert rel["interval"] is None and rel["applicability"] is None
    assert "FEMTO" in rel["interval_reason"] and "FEMTO" in rel["applicability_reason"]


def test_unexpected_failure_withholds_everything(isolated, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret value 123.456")

    monkeypatch.setattr(reliability, "build", boom)
    body = _predict({"a": 0.1, "b": -0.2})
    rel = body["reliability"]
    assert rel["interval"] is None and rel["applicability"] is None
    assert rel["held_out_error"]["available"] is False
    assert rel["tree_disagreement"]["available"] is False
    assert "123.456" not in json.dumps(rel)


@pytest.mark.parametrize("content", [
    "not json",
    json.dumps({"femto_lobo": []}),
    json.dumps({**_metrics(), "femto_lobo_overall_by_model": {"extra_trees": {"mae_seconds": 1}}}),
])
def test_held_out_error_rejects_incomplete_metrics(tmp_path, content):
    path = tmp_path / "rul_evaluation.json"
    path.write_text(content)
    block = reliability.held_out_error(path, "extra_trees")
    assert block["available"] is False and block["reason"]
    assert "mae_seconds" not in block


def test_tree_disagreement_without_trees_is_null_with_reason():
    block, sigma = reliability.tree_disagreement(object(), pd.DataFrame([{"a": 1.0}]))
    assert sigma is None and block["available"] is False and block["reason"]


REAL = ((api.MODELS_DIR / "rul_extra_trees.joblib").exists()
        and (api.MODELS_DIR / api.CROSS_DOMAIN_BUNDLE_NAME).exists())


@pytest.mark.skipif(not REAL, reason="cached model artifacts not mounted")
def test_real_artifacts_produce_traceable_block():
    model = api._load_joblib("rul_extra_trees.joblib")
    body = _predict(dict(model.median_fill))
    rel = body["reliability"]
    assert rel["tree_disagreement"]["available"] is True
    assert rel["tree_disagreement"]["n_trees"] == len(model.model.estimators_)
    assert (rel["interval"] is None) != (rel["interval_reason"] is None)
    assert (rel["applicability"] is None) != (rel["applicability_reason"] is None)
    if rel["interval"] is not None:
        assert rel["interval"]["lower_seconds"] <= body["rul_seconds"] <= rel["interval"][
            "upper_seconds"]
    if not (api.METRICS_DIR / "rul_evaluation.json").exists():
        assert rel["held_out_error"]["available"] is False
    _assert_no_confidence_fields(body)
