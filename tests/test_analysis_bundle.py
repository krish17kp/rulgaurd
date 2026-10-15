"""Round-trip parity tests for `.rulguard.zip` analysis bundles (Phase J)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bearing_pdm.analysis_bundle import (
    BundleValidationError,
    build_bundle,
    build_routing_bundle,
    bundle_kind,
    load_bundle,
)

DEPLOY_DATA_DIR = Path(__file__).resolve().parents[1] / "deploy_data"


def _load_json(name: str) -> dict:
    path = DEPLOY_DATA_DIR / name
    if not path.exists():
        pytest.skip(f"{path} not present in this checkout")
    return json.loads(path.read_text())


def test_femto_bearing_round_trip_matches_cached_trajectory(tmp_path):
    trajectory = _load_json("trajectory_data.json")
    original = trajectory["femto:Bearing2_1"]

    bundle_path = build_bundle("femto:Bearing2_1", original, tmp_path / "bearing2_1.rulguard.zip")
    loaded = load_bundle(bundle_path)

    assert loaded == original
    assert loaded["reference_hi"] == original["reference_hi"]
    assert loaded["held_out_metrics"] == original["held_out_metrics"]
    assert loaded["actual_rul_seconds"] == original["actual_rul_seconds"]


def test_college_trajectory_round_trip_matches_cached_artifact(tmp_path):
    college = _load_json("college_trajectory.json")
    original = college["college:nsk6205"]

    bundle_path = build_bundle("college:nsk6205", original, tmp_path / "college.rulguard.zip")
    loaded = load_bundle(bundle_path)

    assert loaded == original
    assert loaded["walk_forward_overall"] == original["walk_forward_overall"]
    assert loaded["naive_caveat"] == original["naive_caveat"]
    assert loaded["domain_shift_note"] == original["domain_shift_note"]


def test_tampered_dataset_checksum_is_rejected(tmp_path):
    payload = {"dataset_id": "femto:Bearing2_1", "reference_hi": [1.0, 0.5]}
    bundle_path = build_bundle("femto:Bearing2_1", payload, tmp_path / "b.rulguard.zip")

    import zipfile

    with zipfile.ZipFile(bundle_path) as zf:
        manifest = zf.read("manifest.json")
        checksums = zf.read("checksums.json")
    tampered = tmp_path / "tampered.rulguard.zip"
    with zipfile.ZipFile(tampered, "w") as zf:
        zf.writestr("manifest.json", manifest)
        zf.writestr("dataset.json", b'{"dataset_id": "femto:Bearing2_1", "reference_hi": [9.9]}')
        zf.writestr("checksums.json", checksums)

    with pytest.raises(BundleValidationError):
        load_bundle(tampered)


def test_bundle_kind_recognises_routing_shape_for_any_dataset():
    xjtu_payload = {"dataset_id": "xjtu", "profile": {"n_files": 123}, "decisions": {"Bearing1_1": {}}}
    ims_payload = {"dataset_id": "ims", "profile": {"n_files": 10}, "decisions": {"test1_bearing3": {}}}
    assert bundle_kind("xjtu", xjtu_payload) == "routing"
    assert bundle_kind("ims", ims_payload) == "routing"
    assert bundle_kind(None, xjtu_payload) == "routing"  # shape alone is enough


def test_build_routing_bundle_round_trips_and_strips_local_path(tmp_path):
    routing_result = {
        "dataset_id": "xjtu",
        "profile": {"n_files": 15, "sampling_rate_hz": 25600.0},
        "decisions": {"Bearing1_1": {"current": {"status": "ok"}, "applicability": {}}},
        "canonical_path": "/home/krish/private/canonical_xjtu.parquet",
    }
    bundle_path = build_routing_bundle("xjtu", routing_result, tmp_path / "xjtu.rulguard.zip")
    loaded, manifest = load_bundle(bundle_path, with_manifest=True)

    assert manifest["dataset_id"] == "xjtu:routing"
    assert "canonical_path" not in loaded
    assert loaded["decisions"]["Bearing1_1"]["current"]["status"] == "ok"
    assert bundle_kind(manifest["dataset_id"], loaded) == "routing"


def test_missing_member_is_rejected(tmp_path):
    import zipfile

    incomplete = tmp_path / "incomplete.rulguard.zip"
    with zipfile.ZipFile(incomplete, "w") as zf:
        zf.writestr("manifest.json", b"{}")

    with pytest.raises(BundleValidationError):
        load_bundle(incomplete)
