"""Phase F: whole-bearing FEMTO ZIP pipeline, verified against the committed
leave-one-bearing-out trajectory artifact (deploy_data/trajectory_data.json)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from bearing_pdm.archive import LOCAL_FULL_MODE, ZipSecurityError
from bearing_pdm.bearing_archive import (
    REPO_ROOT,
    BearingArchiveError,
    analyze_femto_bearing_zip,
)

BEARING2_1_DIR = REPO_ROOT / "data/interim/femto/Learning_set/Bearing2_1"
TRAJECTORY_JSON = REPO_ROOT / "deploy_data/trajectory_data.json"

requires_bearing2_1 = pytest.mark.skipif(
    not BEARING2_1_DIR.is_dir(), reason="Bearing2_1 learning-set folder not present locally"
)
requires_trajectory_json = pytest.mark.skipif(
    not TRAJECTORY_JSON.is_file(), reason="deploy_data/trajectory_data.json not present"
)


def _zip_of(tmp_path: Path, source_dir: Path, filenames: list[str], arc_prefix: str = "Bearing2_1") -> Path:
    zip_path = tmp_path / "bearing.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name in filenames:
            zf.write(source_dir / name, arcname=f"{arc_prefix}/{name}")
    return zip_path


@requires_bearing2_1
def test_analyze_full_bearing_zip_matches_cached_acquisition_count(tmp_path):
    acc_files = sorted(p.name for p in BEARING2_1_DIR.glob("acc_*.csv"))
    zip_path = _zip_of(tmp_path, BEARING2_1_DIR, acc_files)

    analysis = analyze_femto_bearing_zip(zip_path, limits=LOCAL_FULL_MODE)

    assert analysis.bearing_run_id == "femto:Bearing2_1"
    assert analysis.acquisition_count == len(acc_files)
    assert analysis.sample_rate_hz == 25_600.0
    assert len(analysis.sequence_index) == len(acc_files)
    assert len(analysis.feature_trajectory["vibration_x_rms"]) == len(acc_files)
    assert len(analysis.representative_signals["early"]["vibration_x"]) == 2560
    assert len(analysis.representative_fft["late"]["vibration_y"]["frequency_hz"]) > 0


@requires_bearing2_1
@requires_trajectory_json
def test_full_bearing_zip_hi_stage_match_cached_trajectory_artifact(tmp_path):
    """Correctness anchor: running the real pipeline over the full uploaded ZIP
    must reproduce the SAME reference HI / stage / held-out RUL the Chunk 2
    /trajectory endpoint already serves from deploy_data/trajectory_data.json -
    both are derived from the identical fitted artifacts and the identical
    raw files, so they must agree exactly (floats rounded to the same 4dp)."""
    acc_files = sorted(p.name for p in BEARING2_1_DIR.glob("acc_*.csv"))
    zip_path = _zip_of(tmp_path, BEARING2_1_DIR, acc_files)

    analysis = analyze_femto_bearing_zip(zip_path, limits=LOCAL_FULL_MODE)
    cached = json.loads(TRAJECTORY_JSON.read_text())["femto:Bearing2_1"]

    assert analysis.reference_hi == cached["reference_hi"]
    assert analysis.stage == cached["stage"]
    assert analysis.actual_rul_seconds == cached["actual_rul_seconds"]
    assert analysis.held_out_mae_seconds == cached["held_out_metrics"]["mae_seconds"]
    assert analysis.held_out_predicted_rul_seconds == cached["held_out_predicted_rul_seconds"]["predicted_rul_seconds"]


@requires_bearing2_1
def test_partial_acquisitions_still_analyze_without_held_out_mismatch(tmp_path):
    """A partial upload (not the full bearing) still runs the real pipeline -
    HI/stage/features are per-acquisition and valid for whatever was uploaded,
    while the held-out comparison explicitly covers the full cached run."""
    acc_files = sorted(p.name for p in BEARING2_1_DIR.glob("acc_*.csv"))[:5]
    zip_path = _zip_of(tmp_path, BEARING2_1_DIR, acc_files)

    analysis = analyze_femto_bearing_zip(zip_path, limits=LOCAL_FULL_MODE)

    assert analysis.acquisition_count == 5
    assert len(analysis.reference_hi) == 5
    assert len(analysis.stage) == 5


def test_rejects_non_femto_archive(tmp_path):
    zip_path = tmp_path / "junk.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("readme.txt", "not a bearing archive")

    with pytest.raises(BearingArchiveError):
        analyze_femto_bearing_zip(zip_path)


def test_rejects_multi_bearing_archive(tmp_path):
    zip_path = tmp_path / "two_bearings.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Bearing1_1/acc_00001.csv", "0,0,0,0,0.1,0.2\n" * 2560)
        zf.writestr("Bearing2_1/acc_00001.csv", "0,0,0,0,0.1,0.2\n" * 2560)

    with pytest.raises(BearingArchiveError, match="exactly one bearing"):
        analyze_femto_bearing_zip(zip_path)


def test_zip_security_violations_still_propagate(tmp_path):
    """A traversal entry must always reject the archive - either as a security
    error from archive.py, or earlier as a bogus multi-bearing archive (the
    traversal path's parent directory looks like an extra "bearing" folder to
    the manifest classifier). Either rejection is safe; silent success is not."""
    zip_path = tmp_path / "traversal.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Bearing2_1/acc_00001.csv", "0,0,0,0,0.1,0.2\n" * 2560)
        zf.writestr("../../etc/passwd", "pwned")

    with pytest.raises((ZipSecurityError, BearingArchiveError)):
        analyze_femto_bearing_zip(zip_path)
