"""Generic/unknown-dataset file reading (nightshift universal-ingestion gap A).

Dataset-specific parsing only, same boundary as femto.py/college.py/ims.py/
xjtu.py: this module knows nothing about canonical channels or adapters.py.
It reads a tabular file using the delimiter/header already sniffed by
profiler.py (never re-guessed here) and selects the columns a human mapped
via profiler.apply_manual_mapping().
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
import pandas as pd

# Binary signal formats: one recording per file, each array/channel a column.
SIGNAL_SUFFIXES = {".mat", ".wav"}
MAX_CHANNELS = 16


def _natural_key(path: Path) -> list:
    """file2 before file10: digit runs compare as numbers."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def discover_generic_files(root: str | Path, suffix: str | None = None) -> list[Path]:
    """Tabular files directly under `root` in natural name order (non-recursive: a
    generic dataset's file-ordering semantics are not known, so this does not guess
    at a nested layout the way a dataset-specific adapter can). `suffix` keeps only
    files of the recordings' own format, so a readme.txt beside CSVs is not read."""
    from bearing_pdm.profiler import (
        TABULAR_SUFFIXES,  # deferred: profiler -> adapters -> generic cycle
    )

    root = Path(root)
    files = sorted(
        (p for p in root.iterdir()
         if p.is_file() and not p.name.startswith(".")
         and (p.suffix.lower() in TABULAR_SUFFIXES | SIGNAL_SUFFIXES or p.suffix[1:].isdigit())
         and (suffix is None or p.suffix.lower() == suffix)),
        key=_natural_key,
    )
    if not files:
        raise FileNotFoundError(f"No tabular files found directly under {root}")
    return files


def read_generic_file(path: str | Path, delimiter: str | None, has_header: bool) -> pd.DataFrame:
    """`delimiter`/`has_header` come from profiler.profile_file()'s sniff of a
    sample file in this folder - assumed uniform across the folder, since a
    generic dataset gives no other basis for per-file format detection.

    Columns are always returned stringified ("0", "1", ...) for a headerless
    file, matching profile_file()'s own `str(col)` column naming exactly -
    the mapping produced from a profiler column name must key this the same
    way regardless of whether the source has a header.
    """
    path = Path(path)
    if path.suffix.lower() == ".mat":
        return _read_mat(path)
    if path.suffix.lower() == ".wav":
        return _read_wav(path)[1]
    sep = delimiter if delimiter and delimiter != "whitespace" else r"\s+"
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    df = pd.read_csv(io.StringIO(text), sep=sep, header=0 if has_header else None)
    df.columns = [str(c) for c in df.columns]
    return df


def _read_mat(path: Path) -> pd.DataFrame:
    """Every numeric vector or narrow matrix in a MATLAB file, samples along rows. A
    matrix gives one column per channel (`name[0]`, ...). Scalars (an RPM, a rate) are
    not signals and are left out; columns shorter than the longest are dropped."""
    import scipy.io as sio

    try:
        mat = sio.loadmat(str(path))
    except NotImplementedError as exc:
        raise ValueError(f"{path.name} is a MATLAB v7.3 file, which cannot be read; "
                         "re-save it in MATLAB with save(name, '-v7')") from exc
    cols: dict[str, np.ndarray] = {}
    for name, v in mat.items():
        if name.startswith("__") or not isinstance(v, np.ndarray) or v.ndim != 2 \
                or v.dtype.kind not in "fiu" or v.size < 2:
            continue
        a = v if v.shape[0] >= v.shape[1] else v.T
        if a.shape[1] == 1:
            cols[name] = a[:, 0]
        elif a.shape[1] <= MAX_CHANNELS:
            cols.update({f"{name}[{i}]": a[:, i] for i in range(a.shape[1])})
    if not cols:
        raise ValueError(f"{path.name} holds no numeric signal array")
    n = max(len(c) for c in cols.values())
    return pd.DataFrame({k: c.astype("float64") for k, c in cols.items() if len(c) == n})


def _read_wav(path: Path) -> tuple[float, pd.DataFrame]:
    """(sampling rate from the file header, one column per channel)."""
    from scipy.io import wavfile

    rate, data = wavfile.read(str(path))
    data = data.reshape(len(data), -1)[:, :MAX_CHANNELS].astype("float64")
    return float(rate), pd.DataFrame({f"channel_{i + 1}": data[:, i] for i in range(data.shape[1])})


def wav_sampling_rate(path: str | Path) -> float:
    return _read_wav(Path(path))[0]
