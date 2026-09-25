#!/usr/bin/env python
"""Any supported dataset -> adapter -> canonical feature Parquet (+ manifest).

Usage:
    python scripts/build_canonical_features.py --dataset femto --role learning
    python scripts/build_canonical_features.py --dataset femto --role test_censored
    python scripts/build_canonical_features.py --dataset college
    python scripts/build_canonical_features.py --dataset ims  --root ~/work/external_data/ims
    python scripts/build_canonical_features.py --dataset xjtu --root ~/work/external_data/xjtu/...

FEMTO/college roots default to config/data_paths.toml. Output:
data/processed/canonical_<dataset>[_<role>].parquet (gitignored) and a JSON
manifest beside it recording the source root, bearings, window, code version.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from bearing_pdm.adapters import get_adapter
from bearing_pdm.config import dataset_root, load_data_paths
from bearing_pdm.pipeline import (
    CANONICAL_SCHEMA_VERSION,
    CANONICAL_WINDOW_S,
    build_canonical_features,
)


def _build_one(dataset: str, run) -> pd.DataFrame:
    t0 = time.time()
    df = build_canonical_features(get_adapter(dataset), run)
    print(f"  {run.run_id}: {len(df)} recordings in {time.time() - t0:.0f}s", flush=True)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--root")
    parser.add_argument("--role")
    parser.add_argument("--config", default="config/data_paths.toml")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out-dir", default="data/processed")
    args = parser.parse_args()

    adapter = get_adapter(args.dataset)
    root = Path(args.root).expanduser() if args.root else dataset_root(
        load_data_paths(args.config), args.dataset, args.role)
    runs = adapter.discover(root, role=args.role)
    print(f"{args.dataset}: {len(runs)} bearing(s) under {root}")

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        frames = list(pool.map(_build_one, [args.dataset] * len(runs), runs))
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)

    suffix = f"_{args.role}" if args.role else ""
    out = Path(args.out_dir) / f"canonical_{args.dataset}{suffix}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    code_version = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                  text=True).stdout.strip() or "unknown"
    manifest = {
        "dataset_id": args.dataset, "display_name": adapter.display_name, "role": args.role,
        "source_root": str(root), "n_rows": len(df), "bearings": sorted(df["bearing_run_id"].unique()),
        "window_s": CANONICAL_WINDOW_S, "schema_version": CANONICAL_SCHEMA_VERSION,
        "reference_window": list(adapter.reference_window), "code_version": code_version,
        "created_at": datetime.now(timezone.utc).isoformat(), "runtime_s": round(time.time() - t0, 1),
    }
    out.with_suffix(".json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {out} ({len(df)} rows, {time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
