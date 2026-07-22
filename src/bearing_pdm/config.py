"""Load config/data_paths.toml. No new dependency: stdlib tomllib (py>=3.11)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataPaths:
    college_raw_dir: Path
    femto_training_dir: Path
    femto_test_dir: Path
    femto_validation_dir: Path
    processed_dir: Path
    interim_dir: Path
    duckdb_path: Path


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
