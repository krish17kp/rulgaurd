from pathlib import Path

import pytest

from bearing_pdm.femto import (
    ACC_COLUMNS,
    TEMP_COLUMNS,
    build_temperature_time_index,
    detect_delimiter,
    discover_femto_bearings,
    find_nearest_temperature_index,
    list_acquisition_indices,
    list_temperature_indices,
    read_acceleration,
    read_temperature,
)

FIXTURES = Path(__file__).parent.parent / "data" / "fixtures" / "femto"
BEARING1_1 = FIXTURES / "Bearing1_1"
BEARING2_1 = FIXTURES / "Bearing2_1"


def test_discover_femto_bearings():
    bearings = discover_femto_bearings(FIXTURES, role="learning")
    labels = {b.bearing_label for b in bearings}
    assert labels == {"Bearing1_1", "Bearing2_1"}
    b1 = next(b for b in bearings if b.bearing_label == "Bearing1_1")
    assert b1.condition_id == 1
    assert b1.role == "learning"


def test_discover_femto_bearings_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        discover_femto_bearings(tmp_path / "nope", role="learning")


def test_list_acquisition_indices():
    assert list_acquisition_indices(BEARING1_1) == [1, 2]


def test_list_temperature_indices():
    assert list_temperature_indices(BEARING1_1) == [1]


def test_detect_delimiter_comma():
    assert detect_delimiter(BEARING1_1 / "temp_00001.csv") == ","


def test_detect_delimiter_semicolon():
    assert detect_delimiter(BEARING2_1 / "temp_00001.csv") == ";"


def test_read_acceleration_schema_and_row_count():
    df = read_acceleration(BEARING1_1, 1)
    assert list(df.columns) == ACC_COLUMNS
    assert len(df) == 2560  # confirmed exact in docs/dataset-audit.md


def test_read_acceleration_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        read_acceleration(BEARING1_1, 999)


def test_read_temperature_comma_schema():
    df = read_temperature(BEARING1_1, 1)
    assert list(df.columns) == TEMP_COLUMNS
    assert len(df) > 0


def test_read_temperature_semicolon_schema():
    df = read_temperature(BEARING2_1, 1)
    assert list(df.columns) == TEMP_COLUMNS
    assert len(df) > 0


def test_build_temperature_time_index():
    idx = build_temperature_time_index(BEARING1_1)
    assert idx == {1: pytest.approx(9 * 3600 + 40 * 60 + 47)}


def test_find_nearest_temperature_index_within_tolerance():
    # acc_00001 starts 09:39:39, temp_00001 starts 09:40:47 -> 68s apart.
    result = find_nearest_temperature_index(BEARING1_1, acc_index=1, tolerance_s=90.0)
    assert result == 1


def test_find_nearest_temperature_index_outside_tolerance_returns_none():
    result = find_nearest_temperature_index(BEARING1_1, acc_index=1, tolerance_s=10.0)
    assert result is None


def test_find_nearest_temperature_index_no_temp_files_returns_none(tmp_path):
    bearing_dir = tmp_path / "Bearing9_9"
    bearing_dir.mkdir()
    (bearing_dir / "acc_00001.csv").write_text("9,39,39,65664,0.552,-0.146\n")
    assert find_nearest_temperature_index(bearing_dir, acc_index=1) is None
