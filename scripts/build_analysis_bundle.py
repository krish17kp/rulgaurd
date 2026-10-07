#!/usr/bin/env python
"""Build a `.rulguard.zip` Analysis Bundle from a FEMTO bearing ZIP or a
college trajectory artifact (M12 Phase U).

Usage:
    python scripts/build_analysis_bundle.py --femto-zip Bearing2_1.zip --output Bearing2_1.rulguard.zip
    python scripts/build_analysis_bundle.py --college-trajectory deploy_data/college_trajectory.json --output college.rulguard.zip
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from bearing_pdm.analysis_bundle import build_bundle
from bearing_pdm.bearing_archive import BearingArchiveError, analyze_femto_bearing_zip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--femto-zip", type=Path, help="a single FEMTO bearing ZIP")
    source.add_argument(
        "--college-trajectory", type=Path, help="an already-built college_trajectory.json"
    )
    parser.add_argument("--dataset-id", help="override the bundle's dataset_id")
    parser.add_argument("--output", type=Path, required=True, help="output .rulguard.zip path")
    args = parser.parse_args(argv)

    if args.femto_zip:
        try:
            analysis = analyze_femto_bearing_zip(args.femto_zip)
        except BearingArchiveError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        dataset_id = args.dataset_id or f"femto:{analysis.bearing_run_id}"
        payload = asdict(analysis)
    else:
        payload = json.loads(args.college_trajectory.read_text())
        dataset_id = args.dataset_id or payload.get("dataset_id", "college")

    out_path = build_bundle(dataset_id, payload, args.output)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
