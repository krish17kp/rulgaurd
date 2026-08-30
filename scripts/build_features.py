#!/usr/bin/env python
"""Build feature Parquet + DuckDB lineage for one dataset.

Usage:
    python scripts/build_features.py --dataset college --config config/data_paths.toml
    python scripts/build_features.py --dataset femto --config config/data_paths.toml [--role learning]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from bearing_pdm.college import discover_college_files
from bearing_pdm.config import load_data_paths
from bearing_pdm.femto import discover_femto_bearings
from bearing_pdm.pipeline import build_college_feature_rows, build_femto_feature_rows
from bearing_pdm.storage import (
    ensure_bearing_run,
    ensure_dataset,
    get_connection,
    write_feature_batch,
)

FEMTO_ROLE_DIR_ATTR = {
    "learning": "femto_training_dir",
    "test_censored": "femto_test_dir",
    "full_test": "femto_validation_dir",
}


def _code_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def build_college(paths, con, code_version: str, sample_stride: int = 1) -> None:
    all_files = discover_college_files(paths.college_raw_dir)
    files = all_files[::sample_stride]
    label = "full run" if sample_stride == 1 else f"1-in-{sample_stride} representative sample"
    print(f"[college] {len(files)}/{len(all_files)} files selected ({label}), building windows...")
    ensure_dataset(con, "college", "College run-to-failure (NSK 6205)", "v1")
    ensure_bearing_run(con, "college:nsk6205", "college", "nsk6205", "college_run")

    t0 = time.time()
    rows = list(build_college_feature_rows(files, code_version=code_version))
    print(f"[college] {len(rows)} window rows built in {time.time()-t0:.0f}s")

    batch_id, parquet_path = write_feature_batch(
        rows, dataset_id="college", processed_dir=paths.processed_dir, code_version=code_version, con=con
    )
    print(f"[college] wrote batch {batch_id} -> {parquet_path}")


def build_femto(paths, con, code_version: str, roles: list[str]) -> None:
    ensure_dataset(con, "femto", "FEMTO/PRONOSTIA IEEE PHM 2012", "phm2012-ieee-challenge")

    for role in roles:
        root_dir = getattr(paths, FEMTO_ROLE_DIR_ATTR[role])
        bearings = discover_femto_bearings(root_dir, role=role)
        print(f"[femto:{role}] {len(bearings)} bearings discovered")

        all_rows = []
        for b in bearings:
            ensure_bearing_run(con, f"femto:{b.bearing_label}", "femto", b.bearing_label, role, condition_id=b.condition_id)
            t0 = time.time()
            rows = list(build_femto_feature_rows(b, code_version=code_version))
            print(f"[femto:{role}] {b.bearing_label}: {len(rows)} acquisitions in {time.time()-t0:.0f}s")
            all_rows.extend(rows)

        if all_rows:
            batch_id, parquet_path = write_feature_batch(
                all_rows, dataset_id="femto", processed_dir=paths.processed_dir, code_version=code_version, con=con
            )
            print(f"[femto:{role}] wrote batch {batch_id} -> {parquet_path} ({len(all_rows)} rows)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["college", "femto"], required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--role", choices=["learning", "test_censored", "full_test"], action="append",
        help="FEMTO only; repeatable. Default: learning only (test_censored/full_test are M4 concerns).",
    )
    parser.add_argument(
        "--sample-stride", type=int, default=1,
        help="College only: process every Nth file (command.md section 26.8 review-sample shortcut). Default 1 = full run.",
    )
    args = parser.parse_args()

    paths = load_data_paths(args.config)
    code_version = _code_version()
    con = get_connection(paths.duckdb_path)

    try:
        if args.dataset == "college":
            build_college(paths, con, code_version, sample_stride=args.sample_stride)
        else:
            roles = args.role or ["learning"]
            build_femto(paths, con, code_version, roles)
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
