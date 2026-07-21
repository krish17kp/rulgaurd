import shutil
from datetime import datetime
from pathlib import Path

import pytest

from bearing_pdm.college import (
    COLLEGE_COLUMNS,
    discover_college_files,
    has_header,
    parse_college_timestamp,
    read_college_chunks,
)

FIXTURES = Path(__file__).parent.parent / "data" / "fixtures" / "college"
HEAD_FIXTURE = FIXTURES / "LogFile_2022-06-20-17-00-31_head5000.csv"
TAIL_FIXTURE = FIXTURES / "LogFile_2022-06-26-01-00-31_tail5000.csv"


def test_parse_college_timestamp_valid_name():
    ts = parse_college_timestamp(Path("LogFile_2022-06-20-17-00-31.csv"))
    assert ts == datetime(2022, 6, 20, 17, 0, 31)


def test_parse_college_timestamp_rejects_bad_name():
    with pytest.raises(ValueError):
        parse_college_timestamp(Path("not_a_logfile.csv"))


def test_has_header_false_for_real_data():
    assert has_header(HEAD_FIXTURE) is False


def test_has_header_true_for_header_row(tmp_path):
    p = tmp_path / "LogFile_2022-06-20-17-00-31.csv"
    p.write_text("vibration_x,vibration_y,bearing_temp_c,ambient_temp_c\n0.1,0.2,40.0,25.0\n")
    assert has_header(p) is True


def test_discover_college_files_chronological_order(tmp_path):
    # Real fixture content, correctly-named copies (fixtures use a _headN/_tailN
    # suffix so they aren't picked up as real 129 files by accident elsewhere).
    early = tmp_path / "LogFile_2022-06-20-17-00-31.csv"
    late = tmp_path / "LogFile_2022-06-26-01-00-31.csv"
    shutil.copy(HEAD_FIXTURE, early)
    shutil.copy(TAIL_FIXTURE, late)

    files = discover_college_files(tmp_path)

    assert [f.path.name for f in files] == [
        "LogFile_2022-06-20-17-00-31.csv",
        "LogFile_2022-06-26-01-00-31.csv",
    ]
    assert files[0].sequence_index == 0
    assert files[1].sequence_index == 1
    assert files[0].timestamp < files[1].timestamp


def test_discover_college_files_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        discover_college_files(tmp_path / "does_not_exist")


def test_discover_college_files_empty_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        discover_college_files(tmp_path)


def test_read_college_chunks_bounded_and_valid(tmp_path):
    p = tmp_path / "LogFile_2022-06-20-17-00-31.csv"
    shutil.copy(HEAD_FIXTURE, p)

    total_rows = 0
    max_chunk_len = 0
    for chunk in read_college_chunks(p, chunksize=1000):
        assert list(chunk.columns) == COLLEGE_COLUMNS
        max_chunk_len = max(max_chunk_len, len(chunk))
        total_rows += len(chunk)

    assert total_rows == 5000
    assert max_chunk_len <= 1000  # bounded memory: no chunk exceeds chunksize


def test_read_college_chunks_last_file_temp_exceeds_stop_threshold(tmp_path):
    p = tmp_path / "LogFile_2022-06-26-01-00-31.csv"
    shutil.copy(TAIL_FIXTURE, p)

    max_bearing_temp = max(chunk["bearing_temp_c"].max() for chunk in read_college_chunks(p))

    assert max_bearing_temp > 85.0  # confirms docs/dataset-audit.md finding


def test_read_college_chunks_preserves_nan_without_raising(tmp_path):
    # Real files contain isolated literal 'NaN' sensor dropouts in any
    # column (docs/dataset-audit.md) - the adapter must pass these through,
    # not raise and not fabricate a fill value.
    p = tmp_path / "LogFile_2022-06-20-17-00-31.csv"
    p.write_text(
        "0.1,0.2,40.0,25.0\n"
        "0.1,0.2,NaN,NaN\n"  # real pattern: temperature sensor dropout
        "NaN,NaN,40.1,25.1\n"  # real pattern: vibration sensor dropout
        "0.1,0.2,40.2,25.2\n"
    )

    chunks = list(read_college_chunks(p, chunksize=10))
    df = chunks[0]

    assert len(df) == 4
    assert df["bearing_temp_c"].isna().sum() == 1
    assert df["vibration_x"].isna().sum() == 1


def test_read_college_chunks_raises_on_malformed_row(tmp_path):
    p = tmp_path / "LogFile_2022-06-20-17-00-31.csv"
    p.write_text("0.1,0.2,40.0,25.0\nnot,a,number,row\n")

    with pytest.raises(Exception):
        list(read_college_chunks(p, chunksize=10))
