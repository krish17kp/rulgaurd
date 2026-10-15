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
import hashlib
import json
import sys
from collections.abc import Callable
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
from bearing_pdm.rar_archive import discover_rar_parts, safe_extract_rar
from bearing_pdm.routing import analyze_bearing, candidates_from_bundle, oof_from_predictions

METRICS = Path("reports/metrics")
RAR_SCRATCH_ROOT = Path.home() / ".cache" / "rulguard_rar_scratch"


def _rar_cache_key(part01: Path) -> str:
    """Identity of a multipart RAR set: part filenames + sizes (not mtime -- unreliable
    across filesystems/downloads). Same archive -> same key -> safe to reuse an extraction."""
    parts = discover_rar_parts(part01)
    sig = "|".join(f"{p.name}:{p.stat().st_size}" for p in parts)
    return hashlib.sha1(sig.encode()).hexdigest()[:16]


def _unwrap(dest: Path) -> Path:
    # Archives commonly wrap everything in one top-level folder (e.g. XJTU-SY's
    # "XJTU-SY_Bearing_Datasets/"); unwrap it so --root lands on the real data.
    # Ignore our own cache marker file when deciding what counts as "wrapped".
    while True:
        entries = [e for e in dest.iterdir() if e.name != ".rulguard_extracted_ok"]
        if len(entries) == 1 and entries[0].is_dir():
            dest = entries[0]
        else:
            return dest


def _resolve_root(root: Path, progress: Callable[[str], None] = print) -> Path:
    """If --root is a (multipart) .rar or a folder holding one, extract it first
    (reusing a prior extraction of the same archive if one is cached).

    Offline-only (rar_archive.py is never wired into the Vercel/API path).
    """
    rar_file = root if root.suffix.lower() == ".rar" else next(iter(sorted(root.glob("*.rar"))), None)
    if rar_file is None:
        return root
    import time

    # ponytail: /tmp is commonly a small RAM-backed tmpfs (e.g. 7GB) -- a real
    # multi-GB dataset archive silently OOM/ENOSPC-kills the extraction there.
    # Use the user's home dir's filesystem instead, which has real disk space.
    RAR_SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    key = _rar_cache_key(rar_file)
    dest = RAR_SCRATCH_ROOT / key
    marker = dest / ".rulguard_extracted_ok"
    if marker.exists() and marker.read_text() == key:
        progress(f"Reusing cached extraction of {rar_file.name} at {dest} (same archive identity).")
        return _unwrap(dest)

    size_mb = rar_file.stat().st_size / 1e6
    progress(f"Archive validation: {rar_file.name} ({size_mb:.0f} MB) -> extracting to {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    safe_extract_rar(rar_file, dest)
    n_files = sum(1 for _ in dest.rglob("*") if _.is_file())
    total_bytes = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    marker.write_text(key)
    progress(f"Extraction done in {time.monotonic() - t0:.1f}s: {n_files} files, "
             f"{total_bytes / 1e9:.2f} GB")
    return _unwrap(dest)


def run_analysis(
    root: Path,
    dataset: str | None = None,
    role: str | None = None,
    mapping_path: str | None = None,
    sampling_rate_hz: float | None = None,
    recording_interval_s: float | None = None,
    progress: Callable[[str], None] = print,
) -> str | None:
    """Profile -> adapter -> features -> routing for `root` (a folder, or a (multipart)
    .rar / folder holding one). Writes reports/metrics/routing_<dataset>.{parquet,json}
    and returns the resolved dataset id, or None if no adapter recognised the data and
    no --mapping was given (profiling-only). Shared by the CLI and the Streamlit dashboard.
    """
    root = _resolve_root(root, progress=progress)

    profile = profile_folder(root)
    progress(f"Profile: {profile['n_files']} files, sampling rate {profile['sampling_rate_hz']} "
             f"({profile['sampling_rate_source']})")
    for w in profile["warnings"]:
        progress(f"  warning: {w}")
    for f in profile["files"]:
        for c in f.get("columns", []):
            progress(f"  column {c['name']!r}: canonical={c['canonical']!r} confidence={c['confidence']}")

    if mapping_path:
        if sampling_rate_hz is None:
            raise ValueError("--mapping requires --sampling-rate-hz (never inferred for a generic dataset)")
        mapping = json.loads(Path(mapping_path).read_text())
        mapped_profile = apply_manual_mapping(profile, mapping, sampling_rate_hz=sampling_rate_hz)
        progress(f"Manual mapping accepted: channels_found={mapped_profile['channels_found']}")
        sample_file = profile["files"][0]
        generic_adapter = GenericAdapter(
            mapping=mapping, sampling_rate_hz=sampling_rate_hz,
            delimiter=sample_file.get("delimiter"), has_header=bool(sample_file.get("has_header")),
            recording_interval_s=recording_interval_s,
        )
        ADAPTERS["generic"] = generic_adapter  # ponytail: single-process run, not a server
        dataset = "generic"
        profile = mapped_profile
    else:
        known = [d["dataset_id"] for d in profile["known_datasets"]]
        dataset = dataset or (known[0] if known else None)
        if dataset is None:
            progress("No adapter recognises this folder: profiling only. Pass a mapping to analyze "
                      "it as a generic dataset, or add an adapter (src/bearing_pdm/adapters.py).")
            return None

    adapter = get_adapter(dataset)
    runs = adapter.discover(root, role=role)
    cached = Path("data/processed") / f"canonical_{dataset}{'_' + role if role else ''}.parquet"
    if cached.exists():
        df = pd.read_parquet(cached)
        df = df[df["bearing_run_id"].isin([r.run_id for r in runs])]
        progress(f"Using cached canonical features {cached} ({len(df)} recordings)")
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
        progress(f"{bearing}: now {decision['current']['status']} "
                 f"(model: {decision['current']['model']}); whole-run summary {decision['status']}")
    METRICS.mkdir(parents=True, exist_ok=True)
    pd.concat(frames).to_parquet(METRICS / f"routing_{dataset}.parquet", index=False)
    (METRICS / f"routing_{dataset}.json").write_text(json.dumps(
        {"dataset_id": dataset, "profile": profile, "decisions": decisions,
         "trajectories": trajectories,
         "canonical_path": str(cached) if cached.exists() else None}, indent=2, default=str))
    progress(f"Wrote {METRICS}/routing_{dataset}.parquet/.json")
    return dataset


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
    if args.mapping and args.sampling_rate_hz is None:
        print("--mapping requires --sampling-rate-hz (never inferred for a generic dataset)")
        return 1
    dataset = run_analysis(
        Path(args.root).expanduser(), dataset=args.dataset, role=args.role,
        mapping_path=args.mapping, sampling_rate_hz=args.sampling_rate_hz,
        recording_interval_s=args.recording_interval_s,
    )
    return 0 if dataset is not None or not args.mapping else 1


if __name__ == "__main__":
    sys.exit(main())
