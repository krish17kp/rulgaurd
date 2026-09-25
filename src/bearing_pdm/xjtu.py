"""XJTU-SY bearing run-to-failure adapter (Xi'an Jiaotong University and
Changxing Sumyoung Technology; Wang, Lei, Li, Li, IEEE Trans. Reliability 69(1),
2020). Sources and verification: docs/external-datasets.md.

Layout:

    <root>/35Hz12kN/Bearing1_1/1.csv ... N.csv
    <root>/37.5Hz11kN/Bearing2_1/...
    <root>/40Hz10kN/Bearing3_1/...

Each CSV: header row (Horizontal_vibration_signals, Vertical_vibration_signals),
32,768 samples at 25.6 kHz (1.28 s), one file per minute. File N is the last
acquisition before the test was stopped, so every bearing is a complete
run-to-failure record.

Dataset-specific parsing only (see ims.py for the same boundary).
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

XJTU_SAMPLE_RATE_HZ = 25_600.0
XJTU_RECORDING_INTERVAL_S = 60.0

# condition folder -> (rpm, radial load in N, condition id)
XJTU_CONDITIONS: dict[str, tuple[float, float, int]] = {
    "35Hz12kN": (2100.0, 12_000.0, 1),
    "37.5Hz11kN": (2250.0, 11_000.0, 2),
    "40Hz10kN": (2400.0, 10_000.0, 3),
}

_BEARING_RE = re.compile(r"^Bearing(\d+)_(\d+)$")
_FILE_RE = re.compile(r"^(\d+)\.csv$")
XJTU_COLUMNS = ("Horizontal_vibration_signals", "Vertical_vibration_signals")


def discover_xjtu_bearings(root: str | Path) -> list[tuple[str, Path]]:
    """(condition folder name, bearing dir) for every bearing found under root."""
    root = Path(root)
    found = []
    for condition in XJTU_CONDITIONS:
        cdir = root / condition
        if not cdir.is_dir():
            continue
        found += [(condition, p) for p in sorted(cdir.iterdir())
                  if p.is_dir() and _BEARING_RE.match(p.name)]
    return found


def list_xjtu_files(bearing_dir: str | Path) -> list[Path]:
    """Numeric (not lexical) order: 10.csv comes after 9.csv."""
    files = [(int(m.group(1)), p) for p in Path(bearing_dir).iterdir()
             if (m := _FILE_RE.match(p.name))]
    if not files:
        raise FileNotFoundError(f"No N.csv acquisitions under {bearing_dir}")
    return [p for _, p in sorted(files)]


def read_xjtu_file(path: str | Path) -> pd.DataFrame:
    """Two float columns, header validated rather than assumed."""
    df = pd.read_csv(path, dtype="float64")
    if tuple(df.columns) != XJTU_COLUMNS:
        raise ValueError(f"{path}: unexpected header {list(df.columns)}")
    return df
