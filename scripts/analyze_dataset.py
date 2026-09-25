#!/usr/bin/env python
"""Universal analysis entry point: any folder -> profile -> (adapter) -> routed result.

    INPUT -> PROFILE -> QUALITY -> ADAPTER -> FEATURES -> APPLICABILITY -> RUL | health only

Usage:
    python scripts/analyze_dataset.py --root ~/work/external_data/ims
    python scripts/analyze_dataset.py --root <folder> --dataset xjtu
    python scripts/analyze_dataset.py --root /some/unknown/folder     # profile only

Uses the canonical Parquet from build_canonical_features.py when it exists for the
dataset, otherwise extracts features now. Needs artifacts/models/cross_domain_bundle.joblib
(run_cross_dataset.py). Writes reports/metrics/routing_<dataset>.{parquet,json}.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import joblib
import pandas as pd

from bearing_pdm.adapters import get_adapter
from bearing_pdm.domain import (
    add_self_normalized_features,
    hi_smooth_window,
    reference_window,
    stage_persistence,
)
from bearing_pdm.pipeline import build_canonical_features
from bearing_pdm.profiler import profile_folder
from bearing_pdm.routing import analyze_bearing, candidates_from_bundle, oof_from_predictions

METRICS = Path("reports/metrics")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--dataset")
    parser.add_argument("--role")
    args = parser.parse_args()
    root = Path(args.root).expanduser()

    profile = profile_folder(root)
    print(f"Profile: {profile['n_files']} files, sampling rate {profile['sampling_rate_hz']} "
          f"({profile['sampling_rate_source']})")
    for w in profile["warnings"]:
        print("  warning:", w)
    known = [d["dataset_id"] for d in profile["known_datasets"]]
    dataset = args.dataset or (known[0] if known else None)
    if dataset is None:
        print("No adapter recognises this folder: profiling only. RUL and health indicator "
              "need an adapter mapping it to the canonical format (src/bearing_pdm/adapters.py).")
        return 0

    adapter = get_adapter(dataset)
    runs = adapter.discover(root, role=args.role)
    cached = Path("data/processed") / f"canonical_{dataset}{'_' + args.role if args.role else ''}.parquet"
    if cached.exists():
        df = pd.read_parquet(cached)
        df = df[df["bearing_run_id"].isin([r.run_id for r in runs])]
        print(f"Using cached canonical features {cached} ({len(df)} recordings)")
    else:
        df = pd.concat([build_canonical_features(adapter, r) for r in runs], ignore_index=True)
    df = add_self_normalized_features(df)

    bundle = joblib.load("artifacts/models/cross_domain_bundle.joblib")
    candidates = candidates_from_bundle(bundle)
    pred_path = METRICS / "cross_dataset_predictions.parquet"
    oof = oof_from_predictions(pd.read_parquet(pred_path)) if pred_path.exists() else None

    frames, decisions = [], {}
    for bearing, g in df.groupby("bearing_run_id"):
        thresholds = replace(bundle["stage_thresholds"], persistence=stage_persistence(dataset))
        out, decision = analyze_bearing(g, candidates, bundle["hi_model"],
                                        thresholds, reference_window(dataset),
                                        oof=oof, smooth_window=hi_smooth_window(dataset))
        frames.append(out)
        decisions[bearing] = decision
        print(f"{bearing}: now {decision['current']['status']} "
              f"(model: {decision['current']['model']}); whole-run summary {decision['status']}")
    METRICS.mkdir(parents=True, exist_ok=True)
    pd.concat(frames).to_parquet(METRICS / f"routing_{dataset}.parquet", index=False)
    (METRICS / f"routing_{dataset}.json").write_text(json.dumps(
        {"dataset_id": dataset, "profile": profile, "decisions": decisions,
         "canonical_path": str(cached) if cached.exists() else None}, indent=2, default=str))
    print(f"Wrote {METRICS}/routing_{dataset}.parquet/.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
