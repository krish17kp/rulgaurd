"""Bounded CSV window feature extraction; no model or dataset assumptions."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from bearing_pdm.features import frequency_domain_features, time_domain_features


@dataclass
class WindowReport:
    """Progress; final counts are valid only when completed is True."""

    rows_read: int = 0
    windows_emitted: int = 0
    trailing_partial_rows: int = 0
    peak_rows_held: int = 0
    completed: bool = False


@dataclass(frozen=True)
class WindowFeatures:
    """Features of a complete window; row_stop is exclusive, offsets are zero-based."""

    row_start: int
    row_stop: int
    features: dict[str, float]


def iter_csv_window_features(
    path: str | Path,
    *,
    vibration_column: str,
    window_samples: int,
    overlap_samples: int,
    chunk_rows: int,
    sample_rate_hz: float,
    report: WindowReport,
) -> Iterator[WindowFeatures]:
    """Yield complete fixed-length windows as feature records, in source order.

    Report must be fresh. Exhaust the iterator for a final trailing-partial
    report; close it when abandoning iteration to release the CSV reader.
    No padding, imputation, resampling, or model inference is performed.
    """
    for name, value in (("window_samples", window_samples), ("chunk_rows", chunk_rows),
                        ("overlap_samples", overlap_samples)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if window_samples <= 0 or chunk_rows <= 0:
        raise ValueError("window_samples and chunk_rows must be positive")
    if not 0 <= overlap_samples < window_samples:
        raise ValueError("overlap_samples must be in [0, window_samples)")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if not isinstance(vibration_column, str) or not vibration_column:
        raise ValueError("vibration_column must be a nonempty column name")
    if report != WindowReport():
        raise ValueError("report must be fresh")

    step = window_samples - overlap_samples
    window = np.empty(window_samples, dtype=np.float64)
    filled = 0
    start = 0
    # Explicit dtype prevents chunk-dependent inference. Blank rows remain
    # samples with missing values; dropping them would change window boundaries.
    with pd.read_csv(path, header=0, usecols=[vibration_column],
                     dtype={vibration_column: np.float64}, chunksize=chunk_rows,
                     skip_blank_lines=False) as reader:
        while True:
            try:
                chunk = next(reader)
            except StopIteration:
                break
            values = chunk[vibration_column].to_numpy(copy=False)
            report.rows_read += len(values)
            report.peak_rows_held = max(report.peak_rows_held, len(values) + window_samples)
            offset = 0
            while offset < len(values):
                take = min(window_samples - filled, len(values) - offset)
                window[filled:filled + take] = values[offset:offset + take]
                filled += take
                offset += take
                if filled == window_samples:
                    features = time_domain_features(window, vibration_column)
                    features.update(frequency_domain_features(window, sample_rate_hz, vibration_column))
                    report.windows_emitted += 1
                    yield WindowFeatures(start, start + window_samples, features)
                    # Scalar forward copy avoids an overlap-sized temporary.
                    for i in range(overlap_samples):
                        window[i] = window[step + i]
                    filled = overlap_samples
                    start += step
            # Do not retain the previous chunk while pandas reads the next one.
            del values, chunk
    report.trailing_partial_rows = filled
    report.completed = True
