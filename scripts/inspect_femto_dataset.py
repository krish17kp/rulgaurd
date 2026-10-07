#!/usr/bin/env python
"""Read-only FEMTO dataset/bearing/acquisition explorer (M12 Phase H).

Browses Learning_set / Test_set / Full_Test_Set - from an already-extracted
directory or directly from a zip archive (datasets/femto/*.zip) - without
fitting or extracting anything. Full_Test_Set is explicitly labelled FROZEN
EVALUATION ONLY; this script never calls assert_no_leakage because it never
fits a model, it only lists what is there.

Usage:
    python scripts/inspect_femto_dataset.py data/interim/femto/Learning_set
    python scripts/inspect_femto_dataset.py datasets/femto/Training_set.zip
    python scripts/inspect_femto_dataset.py data/interim/femto/Learning_set --bearing Bearing1_1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bearing_pdm.archive import build_manifest_from_zip
from bearing_pdm.femto import (
    discover_femto_bearings,
    list_acquisition_indices,
    list_temperature_indices,
)

ROLE_WARNING = {
    "full_test": "FROZEN EVALUATION ONLY - never fit/calibrate/tune thresholds against this data.",
    "test_censored": "Censored evaluation input - not for fitting.",
    "learning": "Training/evaluation permitted.",
}


def _infer_role(root: Path) -> str:
    name = root.name.lower()
    if "full_test" in name or "validation" in name:
        return "full_test"
    if "test_set" in name or name == "test_set":
        return "test_censored"
    return "learning"


def _inspect_zip(zip_path: Path) -> int:
    manifest = build_manifest_from_zip(zip_path)
    print(f"archive: {zip_path}")
    print(f"dataset_type: {manifest.dataset_type}")
    print(f"compatibility: {manifest.compatibility}")
    print(f"bearing/run IDs: {sorted(manifest.bearing_run_ids)}")
    print(f"file_count: {manifest.file_count}")
    if manifest.warnings:
        print("warnings:")
        for w in manifest.warnings:
            print(f"  - {w}")
    return 0


def _inspect_dir(root: Path, bearing_filter: str | None) -> int:
    role = _infer_role(root)
    print(f"root: {root}")
    print(f"role: {role}  ({ROLE_WARNING[role]})")
    bearings = discover_femto_bearings(root, role)
    if bearing_filter:
        bearings = [b for b in bearings if b.bearing_label == bearing_filter]
        if not bearings:
            print(f"bearing {bearing_filter!r} not found under {root}", file=sys.stderr)
            return 1
    for b in bearings:
        acc = list_acquisition_indices(b.path)
        temp = list_temperature_indices(b.path)
        print(f"  {b.bearing_label}: {len(acc)} acc files, {len(temp)} temp files")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Extracted FEMTO role directory or a datasets/femto/*.zip archive")
    parser.add_argument("--bearing", default=None, help="Limit to one BearingC_N label")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"not found: {path}", file=sys.stderr)
        return 1
    if path.suffix.lower() == ".zip":
        return _inspect_zip(path)
    return _inspect_dir(path, args.bearing)


if __name__ == "__main__":
    raise SystemExit(main())
