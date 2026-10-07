#!/usr/bin/env python
"""Zero-shot / dataset-specific evaluation workflow for an external bearing
dataset (IMS, XJTU-SY) against the frozen FEMTO model (M12 Phase O/P/Q).

As of this writing neither external dataset is obtainable in the reference
environment: IMS ships its three experiments as `.rar` (no extractor/sudo
available) and XJTU-SY's mirrors (Google Drive/Baidu/Dropbox/MEGA) require
interactive browser auth, not a scriptable download. This CLI exists so the
workflow is ready the moment a human supplies the extracted data; it refuses
to guess dataset structure and fails with a clear message instead.

Usage:
    python scripts/evaluate_external_dataset.py --dataset ims --data-dir /path/to/extracted/IMS
    python scripts/evaluate_external_dataset.py --dataset xjtu --data-dir /path/to/extracted/XJTU-SY
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_LAYOUT = {
    "ims": (
        "Expected the three extracted IMS test folders (e.g. '1st_test/', '2nd_test/', "
        "'3rd_test/') under --data-dir, each containing per-timestamp ASCII vibration files. "
        "Obtain via: download https://data.nasa.gov/docs/legacy/IMS.zip, then extract the three "
        ".rar members with `unrar` or `7z` (requires `sudo apt-get install unrar` or p7zip-full "
        "on this machine)."
    ),
    "xjtu": (
        "Expected XJTU-SY's per-condition bearing folders (e.g. 'Bearing1_1/') of per-minute "
        ".csv files under --data-dir. Obtain via one of the mirrors listed at "
        "https://github.com/WangBiaoXJTU/xjtu-sy-bearing-datasets (Google Drive/Baidu/Dropbox/"
        "MEGA) - these require an interactive browser download, not a scriptable fetch."
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(REQUIRED_LAYOUT), required=True)
    parser.add_argument("--data-dir", type=Path, required=True, help="extracted raw dataset root")
    args = parser.parse_args(argv)

    if not args.data_dir.exists() or not any(args.data_dir.iterdir()):
        print(f"error: --data-dir {args.data_dir} does not exist or is empty.", file=sys.stderr)
        print(REQUIRED_LAYOUT[args.dataset], file=sys.stderr)
        return 1

    # ponytail: real adapter wiring (ims.py / xjtu.py audit, FEMTO zero-shot,
    # dataset-specific held-out model) is implemented once real extracted
    # data is available to verify assumptions against - see module docstring.
    print(
        f"error: {args.dataset} evaluation is not implemented until the real extracted "
        "dataset has been inspected (this project's rules forbid guessing dataset "
        "structure without evidence). Found a non-empty --data-dir; next step is a human "
        "or a follow-up session inspecting its real layout against "
        f"bearing_pdm/{args.dataset}.py before any evaluation code is written.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
