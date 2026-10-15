#!/usr/bin/env python
"""Universal analysis entry point: any folder -> profile -> (adapter) -> routed result.

    INPUT -> PROFILE -> QUALITY -> ADAPTER -> FEATURES -> APPLICABILITY -> RUL | health only

Usage:
    python scripts/analyze_dataset.py --root ~/work/external_data/ims
    python scripts/analyze_dataset.py --root <folder> --dataset xjtu
    python scripts/analyze_dataset.py --root /some/unknown/folder     # profile only

    # Unrecognised dataset: inspect the profile's printed column/confidence
    # table first, write a {column name: canonical role} mapping to a JSON
    # file (roles: vibration_x, vibration_y, temperature_bearing,
    # temperature_ambient, timestamp, rpm, ...), then:
    python scripts/analyze_dataset.py --root <folder> --mapping mapping.json \\
        --sampling-rate-hz 20000 [--recording-interval-s 60]

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

from bearing_pdm.adapters import ADAPTERS, GenericAdapter, get_adapter
from bearing_pdm.domain import (
    add_self_normalized_features,
    hi_smooth_window,
    reference_window,
    stage_persistence,
)
from bearing_pdm.pipeline import build_canonical_features
from bearing_pdm.profiler import apply_manual_mapping, profile_folder
from bearing_pdm.routing import analyze_bearing, candidates_from_bundle, oof_from_predictions

METRICS = Path("reports/metrics")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--dataset")
    parser.add_argument("--role")
    parser.add_argument(
        "--mapping",
        help="JSON file of {column name: canonical role} for a dataset no adapter recognises "
             "(profiler.apply_manual_mapping) - requires --sampling-rate-hz",
    )
    parser.add_argument("--sampling-rate-hz", type=float,
                        help="Required with --mapping: the dataset's documented sampling rate, "
                             "never inferred for a generic mapping")
    parser.add_argument("--recording-interval-s", type=float,
                        help="With --mapping and more than one file: seconds between recordings, "
                             "to build a trajectory; omit for a single-file signal/FFT/features-"
                             "only analysis")
    args = parser.parse_args()
    root = Path(args.root).expanduser()

    profile = profile_folder(root)
    print(f"Profile: {profile['n_files']} files, sampling rate {profile['sampling_rate_hz']} "
          f"({profile['sampling_rate_source']})")
    for w in profile["warnings"]:
        print("  warning:", w)
    for f in profile["files"]:
        for c in f.get("columns", []):
            print(f"  column {c['name']!r}: canonical={c['canonical']!r} confidence={c['confidence']}")

    if args.mapping:
        if args.sampling_rate_hz is None:
            print("--mapping requires --sampling-rate-hz (never inferred for a generic dataset)")
            return 1
        mapping = json.loads(Path(args.mapping).read_text())
        mapped_profile = apply_manual_mapping(profile, mapping, sampling_rate_hz=args.sampling_rate_hz)
        print(f"Manual mapping accepted: channels_found={mapped_profile['channels_found']}")
        sample_file = profile["files"][0]
        generic_adapter = GenericAdapter(
            mapping=mapping, sampling_rate_hz=args.sampling_rate_hz,
            delimiter=sample_file.get("delimiter"), has_header=bool(sample_file.get("has_header")),
            recording_interval_s=args.recording_interval_s,
        )
        ADAPTERS["generic"] = generic_adapter  # ponytail: single-process CLI run, not a server
        dataset = "generic"
        profile = mapped_profile
    else:
        known = [d["dataset_id"] for d in profile["known_datasets"]]
        dataset = args.dataset or (known[0] if known else None)
        if dataset is None:
            print("No adapter recognises this folder: profiling only. Pass --mapping to analyze "
                  "it as a generic dataset, or add an adapter (src/bearing_pdm/adapters.py).")
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

    # Per-recording columns a portable bundle needs to chart a trajectory
    # without shipping the raw dataset (web Results Workspace: HI vs
    # progression, stage transitions, RUL vs progression). Additive to the
    # JSON only; the parquet (full `out` frame) is unchanged.
    _TRAJECTORY_COLUMNS = (
        "sequence_index", "elapsed_s", "health_indicator", "stage",
        "actual_rul_seconds", "rul_status", "predicted_rul_seconds", "rul_lo", "rul_hi",
    )

    frames, decisions, trajectories = [], {}, {}
    for bearing, g in df.groupby("bearing_run_id"):
        thresholds = replace(bundle["stage_thresholds"], persistence=stage_persistence(dataset))
        out, decision = analyze_bearing(g, candidates, bundle["hi_model"],
                                        thresholds, reference_window(dataset),
                                        oof=oof, smooth_window=hi_smooth_window(dataset))
        frames.append(out)
        decisions[bearing] = decision
        present = [c for c in _TRAJECTORY_COLUMNS if c in out]
        trajectories[bearing] = out[present].to_dict(orient="records")
        print(f"{bearing}: now {decision['current']['status']} "
              f"(model: {decision['current']['model']}); whole-run summary {decision['status']}")
    METRICS.mkdir(parents=True, exist_ok=True)
    pd.concat(frames).to_parquet(METRICS / f"routing_{dataset}.parquet", index=False)
    (METRICS / f"routing_{dataset}.json").write_text(json.dumps(
        {"dataset_id": dataset, "profile": profile, "decisions": decisions,
         "trajectories": trajectories,
         "canonical_path": str(cached) if cached.exists() else None}, indent=2, default=str))
    print(f"Wrote {METRICS}/routing_{dataset}.parquet/.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
