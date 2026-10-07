"""Phase I: deploy_data/college_trajectory.json must trace to real committed artifacts,
never fabricated numbers, and must never carry a FEMTO-fit HI/stage onto college (D11)."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPO_ROOT / "deploy_data" / "college_trajectory.json"


def test_artifact_exists_and_has_one_bearing_run():
    data = json.loads(ARTIFACT.read_text())
    assert list(data.keys()) == ["college:nsk6205"], "college is one physical run, not multiple bearings"


def test_walk_forward_metrics_match_committed_evaluation():
    data = json.loads(ARTIFACT.read_text())["college:nsk6205"]
    eval_json = json.loads((REPO_ROOT / "deploy_data" / "rul_evaluation.json").read_text())
    assert data["walk_forward_overall"] == eval_json["college_overall_by_model"]
    assert data["naive_caveat"] == eval_json["college_naive_caveat"]


def test_held_out_predictions_match_committed_predictions_parquet():
    import pandas as pd

    data = json.loads(ARTIFACT.read_text())["college:nsk6205"]
    predictions = pd.read_parquet(REPO_ROOT / "deploy_data" / "rul_predictions.parquet")
    college_pred = predictions[
        (predictions["dataset_id"] == "college") & (predictions["model"] == "extra_trees")
    ].sort_values("sequence_index")
    assert data["held_out_predicted_rul_seconds"]["sequence_index"] == (
        college_pred["sequence_index"].astype(int).tolist()
    )


def test_no_reference_hi_or_stage_applied_to_college():
    data = json.loads(ARTIFACT.read_text())["college:nsk6205"]
    assert "reference_hi" not in data
    assert "stage" not in data
    assert "domain_shift_note" in data


def test_feature_trends_are_real_not_fabricated_placeholders():
    data = json.loads(ARTIFACT.read_text())["college:nsk6205"]
    rms = data["feature_trends"]["vibration_x_rms"]
    assert len(rms) == data["n_acquisitions"]
    assert len({round(v, 6) for v in rms if v is not None}) > 10, "trend must vary, not be a constant placeholder"
