#!/usr/bin/env python
"""Classify a dataset archive, or fully analyze a FEMTO bearing ZIP (M12 Phase U).

Usage:
    python scripts/analyze_archive.py Bearing2_1.zip
    python scripts/analyze_archive.py Bearing2_1.zip --full --output analysis.json
    python scripts/analyze_archive.py Training_set.zip
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from bearing_pdm.archive import build_manifest_from_zip
from bearing_pdm.bearing_archive import BearingArchiveError, analyze_femto_bearing_zip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", type=Path, help="path to a dataset ZIP archive")
    parser.add_argument(
        "--full",
        action="store_true",
        help="run the full FEMTO bearing pipeline instead of just classifying the archive "
        "(only valid for a single-bearing FEMTO ZIP)",
    )
    parser.add_argument("--output", type=Path, help="write JSON result to this path")
    args = parser.parse_args(argv)

    if args.full:
        try:
            result: object = analyze_femto_bearing_zip(args.zip_path)
        except BearingArchiveError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        payload = asdict(result)
    else:
        manifest = build_manifest_from_zip(args.zip_path)
        payload = asdict(manifest)

    text = json.dumps(payload, indent=2, default=str)
    if args.output:
        args.output.write_text(text)
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
