"""Generic/unknown-dataset file reading (nightshift universal-ingestion gap A).

Dataset-specific parsing only, same boundary as femto.py/college.py/ims.py/
xjtu.py: this module knows nothing about canonical channels or adapters.py.
It reads a tabular file using the delimiter/header already sniffed by
profiler.py (never re-guessed here) and selects the columns a human mapped
via profiler.apply_manual_mapping().
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd


def discover_generic_files(root: str | Path) -> list[Path]:
    """Sorted tabular files directly under `root` (non-recursive: a generic
    dataset's file-ordering semantics are not known, so this does not guess
    at a nested layout the way a dataset-specific adapter can)."""
    from bearing_pdm.profiler import (
        TABULAR_SUFFIXES,  # deferred: profiler -> adapters -> generic cycle
    )

    root = Path(root)
    files = sorted(
        p for p in root.iterdir()
        if p.is_file() and not p.name.startswith(".")
        and (p.suffix.lower() in TABULAR_SUFFIXES or p.suffix[1:].isdigit())
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
    sep = delimiter if delimiter and delimiter != "whitespace" else r"\s+"
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    df = pd.read_csv(io.StringIO(text), sep=sep, header=0 if has_header else None)
    df.columns = [str(c) for c in df.columns]
    return df
