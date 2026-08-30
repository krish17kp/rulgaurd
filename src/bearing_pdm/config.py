"""Load config/data_paths.toml. No new dependency: stdlib tomllib (py>=3.11).

Also owns resolution of paths that were *persisted* by an earlier pipeline run
(`resolve_stored_path`), which may have been written on a different OS - see
docs/decisions.md D13.
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# How many trailing segments of a stored path to try when re-rooting it under a
# local dataset directory. 4 covers FEMTO's deepest layout
# (<set>/<subset>/<bearing>/<file>) without matching so loosely that an
# unrelated file with the same name could win.
_MAX_REROOT_SEGMENTS = 4


@dataclass(frozen=True)
class DataPaths:
    college_raw_dir: Path
    femto_training_dir: Path
    femto_test_dir: Path
    femto_validation_dir: Path
    processed_dir: Path
    interim_dir: Path
    duckdb_path: Path

    def source_search_roots(self) -> tuple[Path, ...]:
        """Local dataset directories to search when re-rooting a
        `source_file_path` that was recorded on another machine."""
        return (
            self.college_raw_dir,
            self.femto_training_dir,
            self.femto_test_dir,
            self.femto_validation_dir,
        )


def normalize_stored_path(stored: str | Path) -> Path:
    """Convert a persisted path string to one this OS can open.

    Backslash -> forward slash only. POSIX accepts `/` on paths written by
    Windows, and Windows accepts `/` too, so a single direction is enough.
    (A genuine POSIX filename containing a literal backslash would be mangled
    by this; no such file exists in either dataset, and the alternative -
    every reader failing on Windows-written batches - is far worse.)
    """
    return Path(str(stored).replace("\\", "/"))


def resolve_stored_path(
    stored: str | Path, search_roots: Sequence[str | Path] = ()
) -> Path:
    """Resolve a path persisted by an earlier run, possibly on another OS/machine.

    `feature_batches.parquet_path` (DuckDB) and `source_file_path` (feature rows)
    are written with the separator and root of whichever host built the batch.
    A batch built on Windows records `data\\processed\\femto_<id>.parquet`; on
    POSIX that entire string is one filename containing backslashes, so every
    reader raises FileNotFoundError even though the file is present. This broke
    the dashboard and all three model scripts after the Windows->Linux migration
    (docs/decisions.md D13).

    Resolution order:
      1. Try the path exactly as stored (a real POSIX filename may legitimately
         contain a backslash; testing first costs nothing and avoids mangling it).
      2. Normalise separators; return it if it now exists.
      3. Re-root: try progressively shorter trailing segments under the search
         roots. This recovers an absolute path from another machine
         (`D:/.../Bearing1_1/acc_00001.csv`) when the same file exists locally.
      4. Give up and return the normalised path unchanged, so the caller's own
         missing-file handling reports a sensible name.

    Suffix length is the OUTER loop, roots the inner one, so the longest match
    anywhere always beats a shorter match under an earlier root. The opposite
    nesting silently crosses dataset boundaries: `source_search_roots()` lists
    `femto_test_dir` before `femto_validation_dir`, and those two directories
    hold identically-named bearing folders, so a root-major search resolves a
    `Full_Test_Set/Bearing1_3/acc_00001.csv` path to the `Test_set/` copy on a
    2-segment match before ever trying `Full_Test_Set` at 3 segments - reaching
    across the frozen hold-out boundary. A single-segment (bare filename) match
    is still permitted, because college's stored parent directory was renamed
    (`Vibration_Bearing_RuntoFailure` -> `datasets/college`) and the filename is
    all that survives; it is only ever reached after every longer match failed.

    Never raises - callers already degrade gracefully when a source file is
    unreachable (dashboard.py's raw-signal panels). Note that `_load_batch` is
    NOT one of those: an unresolvable batch path still surfaces as an error.
    """
    raw = Path(str(stored))
    if raw.exists():
        return raw

    path = normalize_stored_path(stored)
    if path.exists():
        return path

    # Drop any anchor ('/', 'D:/', '//server/share/'): joining an anchored
    # segment onto a root discards the root entirely and escapes the search.
    parts = path.parts[1:] if path.anchor and path.parts else path.parts
    if not parts:
        return path

    roots = [Path(r) for r in search_roots if Path(r).is_dir()]
    stored_parts = set(parts)

    for n in range(min(len(parts), _MAX_REROOT_SEGMENTS), 0, -1):
        matches = [
            root for root in roots if root.joinpath(*parts[-n:]).is_file()
        ]
        if not matches:
            continue
        if len(matches) == 1:
            return matches[0].joinpath(*parts[-n:])

        # Ambiguous: the same trailing segments exist under several roots.
        # FEMTO's Test_set/ and Full_Test_Set/ hold identically-named bearing
        # folders, so 'Bearing1_3/acc_00001.csv' matches both. Break the tie on
        # how much of the ROOT's own path the stored path mentions - a stored
        # `.../Validation_Set/Full_Test_Set/...` names 'Full_Test_Set', which
        # the validation root ends with, and never names 'Test_set'.
        scored = sorted(
            matches, key=lambda root: sum(part in stored_parts for part in root.parts), reverse=True
        )
        best = sum(part in stored_parts for part in scored[0].parts)
        runner_up = sum(part in stored_parts for part in scored[1].parts)
        if best > runner_up:
            return scored[0].joinpath(*parts[-n:])

        # Genuinely undecidable. Returning any candidate here risks silently
        # crossing the learning/hold-out boundary, so decline to guess and let
        # the caller's missing-file path report it.
        return path

    return path


def load_data_paths(config_path: str | Path) -> DataPaths:
    """Read data_paths.toml. Raises FileNotFoundError / KeyError with a clear
    message rather than silently defaulting - paths are load-bearing facts."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}. Copy config/data_paths.example.toml "
            "to config/data_paths.toml and set real local paths."
        )
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    try:
        college = raw["college"]
        femto = raw["femto"]
        output = raw["output"]
    except KeyError as e:
        raise KeyError(f"Missing required section {e} in {config_path}") from e

    return DataPaths(
        college_raw_dir=Path(college["raw_dir"]),
        femto_training_dir=Path(femto["training_dir"]),
        femto_test_dir=Path(femto["test_dir"]),
        femto_validation_dir=Path(femto["validation_dir"]),
        processed_dir=Path(output["processed_dir"]),
        interim_dir=Path(output["interim_dir"]),
        duckdb_path=Path(output["duckdb_path"]),
    )
