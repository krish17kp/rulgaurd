"""IMS bearing run-to-failure adapter (University of Cincinnati Center for
Intelligent Maintenance Systems, distributed by the NASA PCoE data repository;
Qiu, Lee, Lin, Yu, J. Sound Vib. 289 (2006)). Sources and verification:
docs/external-datasets.md.

Layout after extracting the NASA archive (`4. Bearings.zip` -> IMS.7z -> *.rar):

    <root>/1st_test/2003.10.22.12.06.24   8 columns: 2 accelerometers per bearing
    <root>/2nd_test/2004.02.12.10.32.39   4 columns: 1 accelerometer per bearing
    <root>/3rd_test/... (ships as 4th_test/txt/ in the archive) 4 columns

Every file: ASCII, whitespace-separated, no header, 20,480 samples at 20 kHz
(1.024 s). The filename IS the acquisition timestamp - there is no time column.

Dataset-specific parsing only; normalisation to the canonical recording happens
in adapters.py (same boundary as femto.py / college.py).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

IMS_SAMPLE_RATE_HZ = 20_000.0
IMS_RPM = 2000.0
# 6000 lbs radial load (NASA readme) = 26.69 kN.
IMS_RADIAL_LOAD_N = 6000 * 4.4482216

_NAME_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})\.(\d{2})\.(\d{2})\.(\d{2})$")

# test id -> (candidate sub-folders, {bearing number: column indices}).
# Test 3's folder is named 4th_test/txt inside the official archive.
IMS_TESTS: dict[str, tuple[tuple[str, ...], dict[int, tuple[int, ...]]]] = {
    "1": (("1st_test",), {1: (0, 1), 2: (2, 3), 3: (4, 5), 4: (6, 7)}),
    "2": (("2nd_test",), {1: (0,), 2: (1,), 3: (2,), 4: (3,)}),
    "3": (("3rd_test", "4th_test/txt", "4th_test"), {1: (0,), 2: (1,), 3: (2,), 4: (3,)}),
}

# Bearings that failed at the end of their test (NASA readme): only these have
# a defined end-of-life, so only these carry a RUL label. The others simply
# survived the test - their remaining life is unknown, not zero.
IMS_FAILED_BEARINGS: dict[tuple[str, int], str] = {
    ("1", 3): "inner race defect",
    ("1", 4): "roller element defect",
    ("2", 1): "outer race failure",
    ("3", 3): "outer race failure",
}


# Documented end of each test (NASA readme). The archived set-3 folder holds
# 6,324 files running to 2004-04-18, but the readme documents 4,448 files ending
# 2004-04-04 19:01:57 - and file #4,448 on disk is exactly that timestamp. The
# 1,876 later files are undocumented, so labelling them as the approach to the
# documented outer-race failure would shift every set-3 RUL label by 13 days on
# no evidence. They are excluded (docs/external-datasets.md, docs/decisions.md D25).
IMS_DOCUMENTED_END: dict[str, datetime] = {"3": datetime(2004, 4, 4, 19, 1, 57)}


def parse_ims_timestamp(path: str | Path) -> datetime:
    """Raises on a non-conforming name: silently skipping a file would corrupt
    elapsed time and every RUL label after it."""
    m = _NAME_RE.match(Path(path).name)
    if not m:
        raise ValueError(f"IMS filename is not YYYY.MM.DD.hh.mm.ss: {Path(path).name}")
    return datetime(*(int(g) for g in m.groups()))


def resolve_test_dir(root: str | Path, test_id: str) -> Path | None:
    root = Path(root)
    for sub in IMS_TESTS[test_id][0]:
        candidate = root / sub
        if candidate.is_dir() and any(_NAME_RE.match(p.name) for p in candidate.iterdir()):
            return candidate
    return None


def list_ims_files(test_dir: str | Path, end: datetime | None = None) -> list[tuple[Path, datetime]]:
    """Chronologically ordered (path, timestamp) for every acquisition file,
    up to and including `end` when given (IMS_DOCUMENTED_END)."""
    files = [p for p in Path(test_dir).iterdir() if p.is_file() and _NAME_RE.match(p.name)]
    if not files:
        raise FileNotFoundError(f"No IMS acquisition files under {test_dir}")
    stamped = sorted(((p, parse_ims_timestamp(p)) for p in files), key=lambda pt: pt[1])
    return [pt for pt in stamped if end is None or pt[1] <= end]


def read_ims_file(path: str | Path, n_columns: int) -> np.ndarray:
    """(n_samples, n_columns) float64. One file is 20,480 rows (~1.3 MB), so a
    whole-file read is already bounded - no chunking needed."""
    df = pd.read_csv(path, sep=r"\s+", header=None, dtype="float64", engine="c")
    if df.shape[1] != n_columns:
        raise ValueError(f"{path}: expected {n_columns} columns, got {df.shape[1]}")
    return df.to_numpy()
