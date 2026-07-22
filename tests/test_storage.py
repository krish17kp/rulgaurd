import shutil
from pathlib import Path

import pandas as pd
import pytest

from bearing_pdm.college import discover_college_files
from bearing_pdm.femto import FemtoBearing
from bearing_pdm.pipeline import build_college_window_rows, build_femto_feature_rows, _college_run_end_timestamp
from bearing_pdm.storage import ensure_bearing_run, ensure_dataset, get_connection, write_feature_batch

COLLEGE_FIXTURES = Path(__file__).parent.parent / "data" / "fixtures" / "college"
FEMTO_FIXTURES = Path(__file__).parent.parent / "data" / "fixtures" / "femto"


def _college_rows(tmp_path):
    shutil.copy(
        COLLEGE_FIXTURES / "LogFile_2022-06-20-17-00-31_head5000.csv",
        tmp_path / "LogFile_2022-06-20-17-00-31.csv",
    )
    files = discover_college_files(tmp_path)
    run_end = _college_run_end_timestamp(files)
    return list(build_college_window_rows(files[0], run_end, window_samples=1000, overlap_fraction=0.5))


def test_get_connection_creates_tables(tmp_path):
    con = get_connection(tmp_path / "meta.duckdb")
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert {"datasets", "bearing_runs", "feature_batches", "acquisitions", "schema_version"} <= tables
    con.close()


def test_ensure_dataset_and_bearing_run_idempotent(tmp_path):
    con = get_connection(tmp_path / "meta.duckdb")
    for _ in range(2):
        ensure_dataset(con, "college", "College run-to-failure", "v1")
        ensure_bearing_run(con, "college:nsk6205", "college", "nsk6205", "college_run")

    assert con.execute("SELECT count(*) FROM datasets").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM bearing_runs").fetchone()[0] == 1
    con.close()


def test_write_feature_batch_college_roundtrip(tmp_path):
    rows = _college_rows(tmp_path)
    con = get_connection(tmp_path / "meta.duckdb")
    ensure_dataset(con, "college", "College run-to-failure", "v1")
    ensure_bearing_run(con, "college:nsk6205", "college", "nsk6205", "college_run")

    batch_id, parquet_path = write_feature_batch(
        rows, dataset_id="college", processed_dir=tmp_path / "processed", code_version="test-sha", con=con
    )

    assert parquet_path.exists()
    df = pd.read_parquet(parquet_path)
    assert len(df) == len(rows)
    assert "vibration_x_rms" in df.columns  # wide features present in Parquet

    batch_row = con.execute(
        "SELECT dataset_id, row_count, schema_version FROM feature_batches WHERE feature_batch_id = ?", [batch_id]
    ).fetchone()
    assert batch_row == ("college", len(rows), "v1")

    acq_count = con.execute(
        "SELECT count(*) FROM acquisitions WHERE feature_batch_id = ?", [batch_id]
    ).fetchone()[0]
    assert acq_count == len(rows)

    # DuckDB must NOT carry the wide feature columns (docs/architecture.md).
    acq_columns = {r[0] for r in con.execute("SELECT * FROM acquisitions LIMIT 0").description}
    assert "vibration_x_rms" not in acq_columns
    con.close()


def test_write_feature_batch_femto_roundtrip(tmp_path):
    bearing = FemtoBearing(bearing_label="Bearing1_1", condition_id=1, role="learning", path=FEMTO_FIXTURES / "Bearing1_1")
    rows = list(build_femto_feature_rows(bearing))

    con = get_connection(tmp_path / "meta.duckdb")
    ensure_dataset(con, "femto", "FEMTO/PRONOSTIA", "phm2012-ieee-challenge")
    ensure_bearing_run(con, "femto:Bearing1_1", "femto", "Bearing1_1", "learning", condition_id=1)

    batch_id, parquet_path = write_feature_batch(
        rows, dataset_id="femto", processed_dir=tmp_path / "processed", code_version="test-sha", con=con
    )

    df = pd.read_parquet(parquet_path)
    assert len(df) == 2
    kind = con.execute("SELECT kind FROM acquisitions WHERE feature_batch_id = ? LIMIT 1", [batch_id]).fetchone()[0]
    assert kind == "femto_acquisition"
    con.close()


def test_write_feature_batch_empty_rows_raises(tmp_path):
    con = get_connection(tmp_path / "meta.duckdb")
    with pytest.raises(ValueError):
        write_feature_batch([], dataset_id="college", processed_dir=tmp_path / "processed", code_version="x", con=con)
    con.close()
