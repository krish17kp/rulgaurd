"""FEMTO-ST / PRONOSTIA adapter.

Folder layout: <root>/BearingC_N/{acc_NNNNN.csv, temp_NNNNN.csv}.
acc: 6 cols, no header, one row per sample (usually 2560 rows @ 25.6kHz).
temp: 5 cols, no header, comma OR semicolon delimited (auto-detected).
See docs/dataset-audit.md for confirmed per-bearing counts and
docs/data-contract.md for the downstream feature-row mapping.

Scope (M1): bearing/role discovery, acquisition listing, acc/temp
parsing with delimiter auto-detection, nearest-wall-clock temperature
alignment. Feature extraction is M2's job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ACC_COLUMNS = ["hour", "minute", "second", "microsecond", "accel_horizontal", "accel_vertical"]
# 4th field's meaning is not documented anywhere verified - kept raw, not overclaimed as microsecond.
TEMP_COLUMNS = ["hour", "minute", "second", "col4_raw", "temperature_c"]

ROLE_LEARNING = "learning"
ROLE_TEST_CENSORED = "test_censored"
ROLE_FULL_TEST = "full_test"

_BEARING_DIR_RE = re.compile(r"^Bearing(\d+)_(\d+)$")
_ACC_RE = re.compile(r"^acc_(\d+)\.csv$", re.IGNORECASE)
_TEMP_RE = re.compile(r"^temp_(\d+)\.csv$", re.IGNORECASE)

# Default tolerance for nearest-wall-clock temp<->acc alignment (seconds).
# Observed temp cadence ~60s vs acc cadence ~10s (docs/dataset-audit.md);
# ponytail: single global constant, revisit if a bearing needs a different value.
DEFAULT_TEMP_ALIGN_TOLERANCE_S = 90.0


@dataclass(frozen=True)
class FemtoBearing:
    bearing_label: str  # e.g. 'Bearing1_1'
    condition_id: int
    role: str
    path: Path


def discover_femto_bearings(root_dir: str | Path, role: str) -> list[FemtoBearing]:
    """List BearingC_N subfolders directly under root_dir (Learning_set,
    Test_set, or Full_Test_Set - caller passes the resolved leaf folder)."""
    root_dir = Path(root_dir)
    if not root_dir.is_dir():
        raise FileNotFoundError(f"FEMTO {role} dir not found: {root_dir}")

    bearings = []
    for p in sorted(root_dir.iterdir()):
        if not p.is_dir():
            continue
        m = _BEARING_DIR_RE.match(p.name)
        if not m:
            continue
        condition_id = int(m.group(1))
        bearings.append(FemtoBearing(bearing_label=p.name, condition_id=condition_id, role=role, path=p))
    if not bearings:
        raise FileNotFoundError(f"No BearingC_N folders found under {root_dir}")
    return bearings


def list_acquisition_indices(bearing_dir: str | Path) -> list[int]:
    """Sorted acc_NNNNN indices present in a bearing folder."""
    bearing_dir = Path(bearing_dir)
    indices = sorted(int(m.group(1)) for p in bearing_dir.iterdir() if (m := _ACC_RE.match(p.name)))
    return indices


def list_temperature_indices(bearing_dir: str | Path) -> list[int]:
    bearing_dir = Path(bearing_dir)
    indices = sorted(int(m.group(1)) for p in bearing_dir.iterdir() if (m := _TEMP_RE.match(p.name)))
    return indices


def detect_delimiter(path: str | Path) -> str:
    with open(path, encoding="utf-8") as f:
        first_line = f.readline()
    comma_count = first_line.count(",")
    semicolon_count = first_line.count(";")
    if semicolon_count > comma_count:
        return ";"
    if comma_count > 0:
        return ","
    raise ValueError(f"Could not detect delimiter (no ',' or ';' found) in {path}")


def read_acceleration(bearing_dir: str | Path, index: int) -> pd.DataFrame:
    path = Path(bearing_dir) / f"acc_{index:05d}.csv"
    df = pd.read_csv(path, header=None, names=ACC_COLUMNS, dtype="float64")
    if df.shape[1] != len(ACC_COLUMNS):
        raise ValueError(f"{path}: expected {len(ACC_COLUMNS)} columns, got {df.shape[1]}")
    if df.isna().any().any():
        raise ValueError(f"{path}: non-numeric or missing value found")
    return df


def read_temperature(bearing_dir: str | Path, index: int) -> pd.DataFrame:
    path = Path(bearing_dir) / f"temp_{index:05d}.csv"
    delimiter = detect_delimiter(path)
    df = pd.read_csv(path, header=None, names=TEMP_COLUMNS, sep=delimiter, dtype="float64")
    if df.shape[1] != len(TEMP_COLUMNS):
        raise ValueError(f"{path}: expected {len(TEMP_COLUMNS)} columns, got {df.shape[1]}")
    if df.isna().any().any():
        raise ValueError(f"{path}: non-numeric or missing value found")
    return df


def _seconds_of_day(row: pd.Series) -> float:
    return row["hour"] * 3600.0 + row["minute"] * 60.0 + row["second"]


def build_temperature_time_index(bearing_dir: str | Path) -> dict[int, float]:
    """Read every temp file's first-row wall-clock time once. Call this once
    per bearing and reuse across all acc-file lookups (O(n_temp) file reads
    total, not O(n_acc * n_temp))."""
    bearing_dir = Path(bearing_dir)
    return {
        t_idx: _seconds_of_day(read_temperature(bearing_dir, t_idx).iloc[0])
        for t_idx in list_temperature_indices(bearing_dir)
    }


def find_nearest_temperature_index(
    bearing_dir: str | Path,
    acc_index: int,
    temp_time_index: dict[int, float] | None = None,
    tolerance_s: float = DEFAULT_TEMP_ALIGN_TOLERANCE_S,
) -> int | None:
    """Nearest-wall-clock-time temp file index for a given acc file, within
    tolerance_s. Returns None (temp_available=False) if no temp files exist
    for this bearing or none fall within tolerance.

    Pass a precomputed `temp_time_index` (from `build_temperature_time_index`)
    when calling this repeatedly for many acc files in the same bearing.

    Uses first-row (hour,minute,second) of each file. All FEMTO runs used
    here span well under 24h (docs/dataset-audit.md), so no day-rollover
    handling is needed - kept unaddressed intentionally rather than guessed.
    """
    bearing_dir = Path(bearing_dir)
    if temp_time_index is None:
        temp_time_index = build_temperature_time_index(bearing_dir)
    if not temp_time_index:
        return None

    acc_first_row = read_acceleration(bearing_dir, acc_index).iloc[0]
    acc_t = _seconds_of_day(acc_first_row)

    best_idx, best_diff = None, None
    for t_idx, t_time in temp_time_index.items():
        diff = abs(t_time - acc_t)
        if best_diff is None or diff < best_diff:
            best_idx, best_diff = t_idx, diff

    if best_idx is None or best_diff > tolerance_s:
        return None
    return best_idx
