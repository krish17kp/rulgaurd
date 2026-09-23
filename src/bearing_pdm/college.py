"""College run-to-failure adapter (Vibration_Bearing_RuntoFailure).

129 hourly CSVs, no header, 4 columns: vibration_x, vibration_y,
bearing_temp_c, ambient_temp_c. See docs/dataset-audit.md for confirmed
facts and docs/data-contract.md for the downstream feature-row mapping.

Scope (M1): file discovery, filename-timestamp parsing, chronological
ordering, header detection, bounded-memory chunked reads, 4-column
validation. Windowing (25,600 samples / 50% overlap) is M2's job
(features.py) - it consumes the chunk generator here.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

COLLEGE_COLUMNS = ["vibration_x", "vibration_y", "bearing_temp_c", "ambient_temp_c"]

_FILENAME_RE = re.compile(
    r"^LogFile_(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})\.csv$"
)


@dataclass(frozen=True)
class CollegeFile:
    path: Path
    timestamp: datetime
    sequence_index: int  # 0-based position in chronological order


def parse_college_timestamp(path: Path) -> datetime:
    """Parse the acquisition timestamp from a LogFile_* filename.

    Raises ValueError on any name that doesn't match - a silently-skipped
    file would corrupt chronological ordering and RUL targets.
    """
    m = _FILENAME_RE.match(path.name)
    if not m:
        raise ValueError(f"Filename does not match LogFile_YYYY-MM-DD-HH-MM-SS.csv: {path.name}")
    year, month, day, hour, minute, second = (int(g) for g in m.groups())
    return datetime(year, month, day, hour, minute, second)


def discover_college_files(raw_dir: str | Path) -> list[CollegeFile]:
    """Discover and chronologically order all LogFile_*.csv in raw_dir.

    Does not hard-code the expected count (129) - callers that need to
    assert a count do so themselves against docs/dataset-audit.md.
    """
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"College raw_dir not found: {raw_dir}")

    candidates = sorted(raw_dir.glob("LogFile_*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No LogFile_*.csv found under {raw_dir}")

    parsed = [(p, parse_college_timestamp(p)) for p in candidates]
    parsed.sort(key=lambda pt: pt[1])
    return [CollegeFile(path=p, timestamp=t, sequence_index=i) for i, (p, t) in enumerate(parsed)]


def has_header(path: str | Path) -> bool:
    """True if the first line is not 4 numeric fields (defensive - the
    audited files have no header, but adapters must not assume forever)."""
    with open(path, encoding="utf-8") as f:
        first_line = f.readline()
    fields = first_line.strip().split(",")
    if len(fields) != len(COLLEGE_COLUMNS):
        return True
    try:
        [float(x) for x in fields]
    except ValueError:
        return True
    return False


def read_college_chunks(
    path: str | Path, chunksize: int = 100_000
) -> Iterator[pd.DataFrame]:
    """Bounded-memory chunked read. Validates column count and that every
    field is either a real float or the literal missing-value marker
    ('NaN'/empty). Raises on true structural malformation (wrong column
    count - pandas itself raises ParserError on a genuinely unparseable
    field). Does NOT raise on NaN: the real files contain isolated sensor
    dropouts (literal 'NaN' strings) in any of the 4 columns - confirmed in
    docs/dataset-audit.md. NaN is preserved as-is (never fabricated,
    interpolated, or forward-filled) so callers can build explicit
    missing-value flags per docs/data-contract.md.
    """
    path = Path(path)
    skiprows = 1 if has_header(path) else 0
    reader = pd.read_csv(
        path,
        header=None,
        names=COLLEGE_COLUMNS,
        skiprows=skiprows,
        chunksize=chunksize,
        dtype="float64",
    )
    for chunk in reader:
        if chunk.shape[1] != len(COLLEGE_COLUMNS):
            raise ValueError(f"{path}: expected {len(COLLEGE_COLUMNS)} columns, got {chunk.shape[1]}")
        yield chunk
