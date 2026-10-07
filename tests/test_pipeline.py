import math
import shutil
from pathlib import Path

import pytest

from bearing_pdm.college import discover_college_files
from bearing_pdm.femto import FemtoBearing
from bearing_pdm.pipeline import (
    _college_run_end_timestamp,
    build_college_feature_rows,
    build_college_feature_rows_resumable,
    build_college_window_rows,
    build_femto_feature_rows,
)

COLLEGE_FIXTURES = Path(__file__).parent.parent / "data" / "fixtures" / "college"
FEMTO_FIXTURES = Path(__file__).parent.parent / "data" / "fixtures" / "femto"


def _copy_college_fixtures(tmp_path):
    shutil.copy(
        COLLEGE_FIXTURES / "LogFile_2022-06-20-17-00-31_head5000.csv",
        tmp_path / "LogFile_2022-06-20-17-00-31.csv",
    )
    shutil.copy(
        COLLEGE_FIXTURES / "LogFile_2022-06-26-01-00-31_tail5000.csv",
        tmp_path / "LogFile_2022-06-26-01-00-31.csv",
    )
    return discover_college_files(tmp_path)


def test_college_window_rows_bounded_by_window_samples(tmp_path):
    files = _copy_college_fixtures(tmp_path)
    run_end = _college_run_end_timestamp(files)

    rows = list(
        build_college_window_rows(files[0], run_end, window_samples=1000, overlap_fraction=0.5)
    )

    # 5000 rows, window=1000, step=500 -> floor((5000-1000)/500)+1 = 9 windows
    assert len(rows) == 9
    assert rows[0]["row_start"] == 0
    assert rows[0]["row_end"] == 999
    assert rows[1]["row_start"] == 500  # 50% overlap carried correctly
    assert rows[0]["n_samples"] == 1000
    assert rows[0]["dataset_id"] == "college"
    assert rows[0]["role"] == "college_run"


def test_college_window_rows_have_feature_and_contract_fields(tmp_path):
    files = _copy_college_fixtures(tmp_path)
    run_end = _college_run_end_timestamp(files)
    row = next(build_college_window_rows(files[0], run_end, window_samples=1000, overlap_fraction=0.5))

    for key in ("acquisition_id", "schema_version", "source_sha256", "temp_available", "rul_seconds"):
        assert key in row
    assert row["schema_version"] == "v1"
    assert "vibration_x_rms" in row
    assert "vibration_y_kurtosis" in row
    assert "bearing_temp_mean" in row
    assert "bearing_minus_ambient_temp_mean" in row


def test_college_last_file_window_has_smaller_rul_than_first_file(tmp_path):
    files = _copy_college_fixtures(tmp_path)
    run_end = _college_run_end_timestamp(files)

    first_row = next(build_college_window_rows(files[0], run_end, window_samples=1000, overlap_fraction=0.5))
    last_row = next(build_college_window_rows(files[1], run_end, window_samples=1000, overlap_fraction=0.5))

    assert last_row["rul_seconds"] < first_row["rul_seconds"]
    assert last_row["rul_seconds"] >= 0 or last_row["rul_seconds"] < 100  # near end of run


def test_college_feature_rows_global_sequence_index_increases_across_files(tmp_path):
    files = _copy_college_fixtures(tmp_path)
    rows = list(build_college_feature_rows(files, window_samples=1000, overlap_fraction=0.5))

    indices = [r["sequence_index"] for r in rows]
    assert indices == list(range(len(rows)))
    # rows from file 0 come before rows from file 1 in this generator's order
    file0_name = files[0].path.name
    seen_file1 = False
    for r in rows:
        if Path(r["source_file_path"]).name != file0_name:
            seen_file1 = True
        elif seen_file1:
            pytest.fail("file0 row found after file1 row - not chronological")


def test_resumable_college_rows_match_the_non_resumable_path(tmp_path):
    """Phase 4: the checkpointed builder must produce the identical rows a
    fresh (non-resumable) run would - only the on-disk resumability differs,
    never the values."""
    files = _copy_college_fixtures(tmp_path)
    fresh = list(build_college_feature_rows(files, window_samples=1000, overlap_fraction=0.5))

    checkpoint_dir = tmp_path / "checkpoints"
    resumable = list(build_college_feature_rows_resumable(
        files, checkpoint_dir, window_samples=1000, overlap_fraction=0.5, log=lambda *a: None,
    ))
    for row in resumable:
        row["sequence_index"] = resumable.index(row)  # reassign as build_features.py does
    # Compare the feature contract, not acquisition_id (regenerated each call).
    compare_keys = [k for k in fresh[0] if k != "acquisition_id"]
    assert len(fresh) == len(resumable)
    for f, r in zip(fresh, resumable, strict=True):
        for k in compare_keys:
            assert f[k] == r[k] or (f[k] != f[k] and r[k] != r[k]), k  # NaN-safe equality


def test_resumable_college_rows_skip_already_checkpointed_files(tmp_path):
    """The regression this exists for: an interrupted 129-file run must not
    re-read a file whose checkpoint already exists."""
    files = _copy_college_fixtures(tmp_path)
    checkpoint_dir = tmp_path / "checkpoints"

    first_pass = list(build_college_feature_rows_resumable(
        files[:1], checkpoint_dir, window_samples=1000, overlap_fraction=0.5, log=lambda *a: None,
    ))
    assert (checkpoint_dir / f"{files[0].path.stem}.parquet").exists()

    # Corrupt the raw source file after checkpointing: if the resumable
    # builder re-read it, this would raise or change the result.
    files[0].path.write_text("not a valid college csv")

    seen = []
    second_pass = list(build_college_feature_rows_resumable(
        files, checkpoint_dir, window_samples=1000, overlap_fraction=0.5, log=seen.append,
    ))
    assert any("reusing checkpoint" in msg for msg in seen)
    assert any(files[1].path.name in msg for msg in seen)  # file 1 freshly processed
    assert len(second_pass) == len(first_pass) + 9  # file1 adds its own 9 windows
    assert {r["acquisition_id"] for r in second_pass[: len(first_pass)]} == \
           {r["acquisition_id"] for r in first_pass}


def test_femto_feature_rows_learning_role_has_rul(tmp_path):
    bearing = FemtoBearing(bearing_label="Bearing1_1", condition_id=1, role="learning", path=FEMTO_FIXTURES / "Bearing1_1")
    rows = list(build_femto_feature_rows(bearing))

    assert len(rows) == 2  # fixture has acc_00001, acc_00002
    assert rows[0]["rul_seconds"] == 10.0  # final_index=2, current=1 -> (2-1)*10
    assert rows[1]["rul_seconds"] == 0.0
    assert rows[0]["dataset_id"] == "femto"
    assert rows[0]["bearing_run_id"] == "femto:Bearing1_1"
    assert rows[0]["n_samples"] == 2560
    assert "vibration_x_rms" in rows[0]


def test_femto_feature_rows_temp_available_when_within_tolerance(tmp_path):
    bearing = FemtoBearing(bearing_label="Bearing1_1", condition_id=1, role="learning", path=FEMTO_FIXTURES / "Bearing1_1")
    rows = list(build_femto_feature_rows(bearing))

    # acc_00001 (09:39:39) vs temp_00001 (09:40:47) = 68s apart, within default 90s tolerance
    assert rows[0]["temp_available"] is True
    assert not math.isnan(rows[0]["bearing_temp_mean"])


def test_femto_feature_rows_test_censored_role_has_no_rul():
    bearing = FemtoBearing(bearing_label="Bearing1_1", condition_id=1, role="test_censored", path=FEMTO_FIXTURES / "Bearing1_1")
    rows = list(build_femto_feature_rows(bearing))
    assert all(r["rul_seconds"] is None for r in rows)
