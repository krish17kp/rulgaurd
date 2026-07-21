"""Parquet feature-batch storage + DuckDB lineage (docs/database-schema.md).

Wide feature vectors live only in Parquet. DuckDB stores identifiers,
paths, hashes, and lineage - never raw feature values (docs/architecture.md:
"why raw high-frequency samples remain outside the database" applies
equally to derived feature columns; keeps the DB small and queryable).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pandas as pd

from bearing_pdm.pipeline import SCHEMA_VERSION, sha256_file

_DDL_STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT current_timestamp)",
    "CREATE TABLE IF NOT EXISTS datasets (dataset_id VARCHAR PRIMARY KEY, display_name VARCHAR NOT NULL, version VARCHAR NOT NULL, description VARCHAR)",
    """CREATE TABLE IF NOT EXISTS bearing_runs (
        bearing_run_id VARCHAR PRIMARY KEY, dataset_id VARCHAR NOT NULL, bearing_label VARCHAR NOT NULL,
        condition_id INTEGER, role VARCHAR NOT NULL, operating_speed_rpm_min DOUBLE,
        operating_speed_rpm_max DOUBLE, load_description VARCHAR
    )""",
    """CREATE TABLE IF NOT EXISTS feature_batches (
        feature_batch_id VARCHAR PRIMARY KEY, dataset_id VARCHAR NOT NULL, schema_version VARCHAR NOT NULL,
        parquet_path VARCHAR NOT NULL, row_count INTEGER NOT NULL, code_version VARCHAR NOT NULL,
        sha256 VARCHAR NOT NULL, created_at TIMESTAMP DEFAULT current_timestamp
    )""",
    """CREATE TABLE IF NOT EXISTS acquisitions (
        acquisition_id VARCHAR PRIMARY KEY, bearing_run_id VARCHAR NOT NULL, kind VARCHAR NOT NULL,
        source_file_path VARCHAR NOT NULL, sequence_index INTEGER NOT NULL, row_start BIGINT, row_end BIGINT,
        event_timestamp TIMESTAMP, sample_rate_hz DOUBLE NOT NULL, n_samples INTEGER NOT NULL,
        temp_available BOOLEAN NOT NULL, source_sha256 VARCHAR NOT NULL,
        feature_batch_id VARCHAR REFERENCES feature_batches(feature_batch_id), feature_row_index INTEGER,
        rul_seconds DOUBLE, stage_label VARCHAR
    )""",
]

_FEATURE_BATCH_COLUMNS = {
    "dataset_id", "schema_version", "parquet_path", "row_count", "code_version", "sha256",
}
_ACQUISITION_COLUMNS = [
    "acquisition_id", "bearing_run_id", "kind", "source_file_path", "sequence_index", "row_start", "row_end",
    "event_timestamp", "sample_rate_hz", "n_samples", "temp_available", "source_sha256",
    "feature_batch_id", "feature_row_index", "rul_seconds", "stage_label",
]


def get_connection(duckdb_path: str | Path) -> duckdb.DuckDBPyConnection:
    path = Path(duckdb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    for stmt in _DDL_STATEMENTS:
        con.execute(stmt)
    con.execute(
        "INSERT INTO schema_version SELECT 1, current_timestamp "
        "WHERE NOT EXISTS (SELECT 1 FROM schema_version WHERE version = 1)"
    )
    return con


def ensure_dataset(con: duckdb.DuckDBPyConnection, dataset_id: str, display_name: str, version: str) -> None:
    con.execute(
        "INSERT INTO datasets SELECT ?, ?, ?, NULL WHERE NOT EXISTS (SELECT 1 FROM datasets WHERE dataset_id = ?)",
        [dataset_id, display_name, version, dataset_id],
    )


def ensure_bearing_run(
    con: duckdb.DuckDBPyConnection,
    bearing_run_id: str,
    dataset_id: str,
    bearing_label: str,
    role: str,
    condition_id: int | None = None,
) -> None:
    con.execute(
        "INSERT INTO bearing_runs SELECT ?, ?, ?, ?, ?, NULL, NULL, NULL "
        "WHERE NOT EXISTS (SELECT 1 FROM bearing_runs WHERE bearing_run_id = ?)",
        [bearing_run_id, dataset_id, bearing_label, condition_id, role, bearing_run_id],
    )


def write_feature_batch(
    rows: list[dict],
    dataset_id: str,
    processed_dir: str | Path,
    code_version: str,
    con: duckdb.DuckDBPyConnection,
) -> tuple[str, Path]:
    """Write rows to Parquet, record the batch + per-acquisition lineage in
    DuckDB. Returns (feature_batch_id, parquet_path). Raises if rows is
    empty - an empty batch is a caller bug, not a valid state to persist."""
    if not rows:
        raise ValueError("write_feature_batch called with zero rows")

    kind = "college_window" if dataset_id == "college" else "femto_acquisition"
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)

    feature_batch_id = str(uuid.uuid4())
    parquet_path = processed_dir / f"{dataset_id}_{feature_batch_id}.parquet"

    df = pd.DataFrame(rows)
    df.to_parquet(parquet_path, index=False)
    batch_sha256 = sha256_file(parquet_path)

    con.execute(
        "INSERT INTO feature_batches VALUES (?, ?, ?, ?, ?, ?, ?, current_timestamp)",
        [feature_batch_id, dataset_id, SCHEMA_VERSION, str(parquet_path), len(df), code_version, batch_sha256],
    )

    source_cols = [c for c in _ACQUISITION_COLUMNS if c not in ("kind", "feature_batch_id", "feature_row_index")]
    acq_df = df[source_cols].copy()
    acq_df["kind"] = kind
    acq_df["feature_batch_id"] = feature_batch_id
    acq_df["feature_row_index"] = range(len(df))
    acq_df = acq_df[_ACQUISITION_COLUMNS]
    con.execute("INSERT INTO acquisitions SELECT * FROM acq_df")

    return feature_batch_id, parquet_path
