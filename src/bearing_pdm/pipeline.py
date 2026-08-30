"""Assemble canonical feature rows (docs/data-contract.md) from the raw
adapters (college.py, femto.py) and the formulas in features.py.

College: chunk-safe sliding window (25,600 samples / 50% overlap default,
config/project.example.toml), overlap carried across chunk boundaries via
an in-memory buffer bounded to ~2x window size.
FEMTO: one row per full acceleration acquisition (2560 samples, not
subdivided), temperature aligned via femto.build_temperature_time_index.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from bearing_pdm.college import CollegeFile, read_college_chunks
from bearing_pdm.features import (
    frequency_domain_features,
    temperature_features,
    time_domain_features,
)
from bearing_pdm.femto import (
    FemtoBearing,
    build_temperature_time_index,
    find_nearest_temperature_index,
    list_acquisition_indices,
    read_acceleration,
    read_temperature,
)

SCHEMA_VERSION = "v1"
DEFAULT_SAMPLE_RATE_HZ = 25600.0
DEFAULT_COLLEGE_WINDOW_SAMPLES = 25600
DEFAULT_COLLEGE_OVERLAP_FRACTION = 0.5
# Confirmed in docs/dataset-audit.md: 2,000,001 rows/file at 25.6kHz.
COLLEGE_FILE_DURATION_S = 2_000_000 / DEFAULT_SAMPLE_RATE_HZ


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _college_run_end_timestamp(files: list[CollegeFile]) -> datetime:
    """Best-estimate end-of-run timestamp: last file's start time plus its
    full nominal duration (~78.125s). More accurate than using the last
    file's start time alone. ponytail: a documented v1 hypothesis, not the
    exact failure instant - revisit if the review needs finer precision."""
    return files[-1].timestamp + timedelta(seconds=COLLEGE_FILE_DURATION_S)


def build_college_window_rows(
    college_file: CollegeFile,
    run_end_timestamp: datetime,
    window_samples: int = DEFAULT_COLLEGE_WINDOW_SAMPLES,
    overlap_fraction: float = DEFAULT_COLLEGE_OVERLAP_FRACTION,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
    code_version: str = "unknown",
) -> Iterator[dict]:
    """Sliding windows over one college file. Final incomplete window is
    dropped (docs/data-contract.md default `keep_incomplete_window=false`)."""
    step = int(window_samples * (1 - overlap_fraction))
    if step <= 0:
        raise ValueError("overlap_fraction must be < 1")

    source_sha256 = sha256_file(college_file.path)
    buffer: pd.DataFrame | None = None
    row_offset = 0
    window_index = 0

    for chunk in read_college_chunks(college_file.path):
        buffer = chunk if buffer is None else pd.concat([buffer, chunk], ignore_index=True)
        while len(buffer) >= window_samples:
            window = buffer.iloc[:window_samples]
            row_start = row_offset
            row_end = row_offset + window_samples - 1
            event_timestamp = college_file.timestamp + timedelta(seconds=row_start / sample_rate_hz)

            row: dict = {
                "acquisition_id": str(uuid.uuid4()),
                "dataset_id": "college",
                "bearing_run_id": "college:nsk6205",
                "role": "college_run",
                # as_posix() keeps the batch readable on either OS (D13).
                "source_file_path": Path(college_file.path).as_posix(),
                "sequence_index": window_index,
                "event_timestamp": event_timestamp,
                "sample_rate_hz": sample_rate_hz,
                "n_samples": window_samples,
                "row_start": row_start,
                "row_end": row_end,
                "schema_version": SCHEMA_VERSION,
                "source_sha256": source_sha256,
                "code_version": code_version,
                "temp_available": bool(window["bearing_temp_c"].notna().any()),
                "rul_seconds": (run_end_timestamp - event_timestamp).total_seconds(),
                "stage_label": None,
            }
            row.update(time_domain_features(window["vibration_x"].to_numpy(), "vibration_x"))
            row.update(time_domain_features(window["vibration_y"].to_numpy(), "vibration_y"))
            row.update(frequency_domain_features(window["vibration_x"].to_numpy(), sample_rate_hz, "vibration_x"))
            row.update(frequency_domain_features(window["vibration_y"].to_numpy(), sample_rate_hz, "vibration_y"))
            row.update(temperature_features(window["bearing_temp_c"].to_numpy(), "bearing_temp"))
            row.update(temperature_features(window["ambient_temp_c"].to_numpy(), "ambient_temp"))
            diff = window["bearing_temp_c"].to_numpy() - window["ambient_temp_c"].to_numpy()
            row.update(temperature_features(diff, "bearing_minus_ambient_temp"))

            yield row

            buffer = buffer.iloc[step:].reset_index(drop=True)
            row_offset += step
            window_index += 1


def build_college_feature_rows(
    files: list[CollegeFile], code_version: str = "unknown", **window_kwargs
) -> Iterator[dict]:
    """Whole-run entry point: assigns a globally increasing sequence_index
    across all 129 files in chronological order."""
    run_end_timestamp = _college_run_end_timestamp(files)
    global_index = 0
    for f in files:
        for row in build_college_window_rows(f, run_end_timestamp, code_version=code_version, **window_kwargs):
            row["sequence_index"] = global_index
            yield row
            global_index += 1


# FEMTO acquisitions carry only time-of-day (no date) - see docs/dataset-audit.md.
# A fixed placeholder date makes them valid datetimes without overclaiming a real date.
_FEMTO_PLACEHOLDER_DATE = date(1900, 1, 1)


def _femto_time_to_datetime(row: pd.Series) -> datetime:
    return datetime.combine(_FEMTO_PLACEHOLDER_DATE, datetime.min.time()) + timedelta(
        hours=row["hour"], minutes=row["minute"], seconds=row["second"]
    )


def build_femto_feature_rows(
    bearing: FemtoBearing,
    code_version: str = "unknown",
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
) -> Iterator[dict]:
    """One row per acc_NNNNN.csv acquisition. rul_seconds is only computed
    for role='learning' (10s/acquisition cadence, confirmed in
    docs/dataset-audit.md) - test_censored/full_test stay NULL here by
    design (docs/data-contract.md: no leakage into the automatic pipeline;
    hidden-RUL derivation is a separate, explicit M4 step)."""
    acc_indices = list_acquisition_indices(bearing.path)
    temp_time_index = build_temperature_time_index(bearing.path)
    final_index = max(acc_indices) if bearing.role == "learning" else None

    for seq, acc_index in enumerate(acc_indices):
        acc_df = read_acceleration(bearing.path, acc_index)
        acc_path = bearing.path / f"acc_{acc_index:05d}.csv"
        event_timestamp = _femto_time_to_datetime(acc_df.iloc[0])

        temp_idx = find_nearest_temperature_index(bearing.path, acc_index, temp_time_index=temp_time_index)
        temp_available = temp_idx is not None

        row: dict = {
            "acquisition_id": str(uuid.uuid4()),
            "dataset_id": "femto",
            "bearing_run_id": f"femto:{bearing.bearing_label}",
            "role": bearing.role,
            # as_posix() keeps the batch readable on either OS (D13).
            "source_file_path": Path(acc_path).as_posix(),
            "sequence_index": seq,
            "event_timestamp": event_timestamp,
            "sample_rate_hz": sample_rate_hz,
            "n_samples": len(acc_df),
            "row_start": None,
            "row_end": None,
            "schema_version": SCHEMA_VERSION,
            "source_sha256": sha256_file(acc_path),
            "code_version": code_version,
            "temp_available": temp_available,
            "rul_seconds": (final_index - acc_index) * 10.0 if final_index is not None else None,
            "stage_label": None,
        }
        row.update(time_domain_features(acc_df["accel_horizontal"].to_numpy(), "vibration_x"))
        row.update(time_domain_features(acc_df["accel_vertical"].to_numpy(), "vibration_y"))
        row.update(frequency_domain_features(acc_df["accel_horizontal"].to_numpy(), sample_rate_hz, "vibration_x"))
        row.update(frequency_domain_features(acc_df["accel_vertical"].to_numpy(), sample_rate_hz, "vibration_y"))

        if temp_available:
            temp_df = read_temperature(bearing.path, temp_idx)
            row.update(temperature_features(temp_df["temperature_c"].to_numpy(), "bearing_temp"))
        else:
            row.update(temperature_features(pd.Series([], dtype="float64").to_numpy(), "bearing_temp"))

        yield row
