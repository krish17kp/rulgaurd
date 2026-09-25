#!/usr/bin/env python
"""Full data-quality audit of one dataset (every sample of every recording).

Usage:
    python scripts/audit_dataset.py --dataset college
    python scripts/audit_dataset.py --dataset xjtu --root ~/work/external_data/xjtu/...

Writes reports/metrics/audit_<dataset>.parquet (per recording) and
reports/metrics/audit_<dataset>.json (summary per bearing).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from bearing_pdm.adapters import get_adapter
from bearing_pdm.config import dataset_root, load_data_paths
from bearing_pdm.profiler import audit_recordings, profile_folder, summarize_audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--root")
    parser.add_argument("--role")
    parser.add_argument("--config", default="config/data_paths.toml")
    args = parser.parse_args()

    adapter = get_adapter(args.dataset)
    root = Path(args.root).expanduser() if args.root else dataset_root(
        load_data_paths(args.config), args.dataset, args.role)
    report = {"dataset_id": args.dataset, "profile": profile_folder(root), "bearings": {}}
    frames = []
    for run in adapter.discover(root, role=args.role):
        audit = audit_recordings(adapter, run)
        report["bearings"][run.run_id] = summarize_audit(audit, run.recording_interval_s)
        frames.append(audit.assign(bearing_run_id=run.run_id))
        print(run.run_id, json.dumps(report["bearings"][run.run_id], default=str)[:400])
    out = Path("reports/metrics")
    out.mkdir(parents=True, exist_ok=True)
    pd.concat(frames).to_parquet(out / f"audit_{args.dataset}.parquet", index=False)
    (out / f"audit_{args.dataset}.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {out}/audit_{args.dataset}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
