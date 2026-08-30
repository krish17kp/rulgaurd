import shutil
import uuid
from pathlib import Path

import pandas as pd
import pytest

from bearing_pdm.college import discover_college_files
from bearing_pdm.femto import FemtoBearing
from bearing_pdm.pipeline import (
    _college_run_end_timestamp,
    build_college_window_rows,
    build_femto_feature_rows,
)
from bearing_pdm.storage import (
    ensure_bearing_run,
    ensure_dataset,
    get_connection,
    latest_batch_parquet,
    write_feature_batch,
)

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


def test_feature_batch_records_a_portable_posix_path(tmp_path):
    """Regression for docs/decisions.md D13: the batch path was stored with
    str(), so a batch built on Windows recorded `...\\...` and every reader
    (dashboard + all three model scripts) raised FileNotFoundError on Linux."""
    rows = _college_rows(tmp_path)
    con = get_connection(tmp_path / "meta.duckdb")
    ensure_dataset(con, "college", "College run-to-failure", "v1")
    ensure_bearing_run(con, "college:nsk6205", "college", "nsk6205", "college_run")

    batch_id, _ = write_feature_batch(
        rows, dataset_id="college", processed_dir=tmp_path / "processed", code_version="test-sha", con=con
    )

    stored = con.execute(
        "SELECT parquet_path FROM feature_batches WHERE feature_batch_id = ?", [batch_id]
    ).fetchone()[0]
    assert "\\" not in stored, f"non-portable separator persisted: {stored!r}"

    stored_source = con.execute(
        "SELECT source_file_path FROM acquisitions WHERE feature_batch_id = ? LIMIT 1", [batch_id]
    ).fetchone()[0]
    assert "\\" not in stored_source, f"non-portable separator persisted: {stored_source!r}"
    con.close()


def test_write_feature_batch_empty_rows_raises(tmp_path):
    con = get_connection(tmp_path / "meta.duckdb")
    with pytest.raises(ValueError):
        write_feature_batch([], dataset_id="college", processed_dir=tmp_path / "processed", code_version="x", con=con)
    con.close()


def test_latest_batch_parquet_role_filter_skips_a_newer_wrong_role_batch(tmp_path):
    """Regression for docs/decisions.md D15. Once a test_censored batch exists it
    is the NEWEST femto batch, so an unfiltered 'latest batch' query returns it
    and every learning-role caller silently gets zero rows. train_models.py
    failed with an opaque sklearn 'at least one array or dtype is required'."""
    rows = _college_rows(tmp_path)
    con = get_connection(tmp_path / "meta.duckdb")
    ensure_dataset(con, "femto", "FEMTO/PRONOSTIA", "phm2012-ieee-challenge")
    ensure_bearing_run(con, "femto:Bearing1_1", "femto", "Bearing1_1", "learning", condition_id=1)
    ensure_bearing_run(con, "femto:Bearing1_3", "femto", "Bearing1_3", "test_censored", condition_id=1)

    def _as(bearing_run_id: str, role: str) -> list[dict]:
        # Fresh acquisition_ids: they are the acquisitions primary key, so the
        # two batches must not reuse the ids generated for `rows`. The `role`
        # column is what latest_batch_parquet reads - bearing_runs.role is
        # insert-once and cannot distinguish these (D15).
        return [
            dict(r, dataset_id="femto", bearing_run_id=bearing_run_id, role=role,
                 acquisition_id=str(uuid.uuid4()))
            for r in rows
        ]

    learning_id, _ = write_feature_batch(
        _as("femto:Bearing1_1", "learning"), dataset_id="femto",
        processed_dir=tmp_path / "p", code_version="v", con=con,
    )
    censored_id, _ = write_feature_batch(
        _as("femto:Bearing1_3", "test_censored"), dataset_id="femto",
        processed_dir=tmp_path / "p", code_version="v", con=con,
    )
    assert learning_id != censored_id

    # Unfiltered: newest wins, which is the censored batch.
    assert censored_id in str(latest_batch_parquet(con, "femto"))
    # Filtered: must reach past it to the learning batch.
    assert learning_id in str(latest_batch_parquet(con, "femto", role="learning"))
    assert censored_id in str(latest_batch_parquet(con, "femto", role="test_censored"))
    con.close()


def test_latest_batch_parquet_returns_none_when_no_batch_matches(tmp_path):
    con = get_connection(tmp_path / "meta.duckdb")
    assert latest_batch_parquet(con, "femto") is None
    assert latest_batch_parquet(con, "femto", role="learning") is None
    con.close()
