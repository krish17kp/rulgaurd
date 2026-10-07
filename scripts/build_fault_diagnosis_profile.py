#!/usr/bin/env python
"""Precompute a compact, committed summary of fault-diagnosis-only external
datasets (CWRU today) for the /evaluation/cross-dataset endpoint and the
Next.js cross-dataset page - same pattern as build_trajectory_data.py /
build_college_trajectory.py: compute once from real data, commit the small
derived JSON, never refit or re-score on request.

CWRU has no run-to-failure RUL target (docs/external-datasets.md) - this
artifact intentionally carries NO mae_seconds/rul fields, only dataset
profile + a real applicability check against the frozen FEMTO model, so
nothing downstream can mistakenly average it into the RUL comparison table.

Usage (repo root): PYTHONPATH=src python scripts/build_fault_diagnosis_profile.py
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from bearing_pdm.applicability import assess as applicability_assess
from bearing_pdm.cwru import DATASET_TYPE, extract_features
from bearing_pdm.routing import candidates_from_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
CWRU_FIXTURES = REPO_ROOT / "data" / "fixtures" / "cwru"
BUNDLE_PATH = REPO_ROOT / "artifacts" / "models" / "cross_domain_bundle.joblib"
OUT_PATH = REPO_ROOT / "deploy_data" / "fault_diagnosis_datasets.json"

CWRU_FILES = {
    "97": "normal baseline",
    "105": "inner race fault 0.007in",
    "118": "ball fault 0.007in",
    "130": "outer race fault 0.007in @6:00",
}
CWRU_SAMPLE_RATE_HZ = 12_000.0


def build_cwru_entry() -> dict:
    entry: dict = {
        "dataset": "CWRU (Case Western Reserve University Bearing Data Center)",
        "dataset_type": DATASET_TYPE,
        "source": "https://engineering.case.edu/bearingdatacenter/download-data-file",
        "sampling_rate_hz": CWRU_SAMPLE_RATE_HZ,
        "channels": ["vibration_x (drive-end accelerometer)"],
        "conditions": [{"file_id": k, "label": v} for k, v in CWRU_FILES.items()],
        "rul_supported": False,
        "rul_unavailable_reason": (
            "CWRU records single fixed-condition snapshots, not a degradation "
            "trajectory - there is no elapsed-time axis and no true RUL target."
        ),
        "applicability": None,
    }

    if not BUNDLE_PATH.exists():
        entry["applicability_unavailable_reason"] = "cross_domain_bundle.joblib not present at build time"
        return entry

    bundle = joblib.load(BUNDLE_PATH)
    candidates = [c for c in candidates_from_bundle(bundle) if c.name == "raw_seconds"]
    if not candidates:
        entry["applicability_unavailable_reason"] = "no raw_seconds candidate in cross_domain_bundle.joblib"
        return entry
    model = candidates[0].applicability

    rows = []
    for file_id in CWRU_FILES:
        features = extract_features(CWRU_FIXTURES / f"{file_id}.mat", file_id, sample_rate_hz=CWRU_SAMPLE_RATE_HZ)
        rows.append({c: features.get(c, np.nan) for c in model.feature_columns})
    df = pd.DataFrame(rows, dtype=float)
    result = applicability_assess(df, model, single_recording=False)
    entry["applicability"] = {
        "level": result["level"],
        "shift_ratio": result["shift_ratio"],
        "reasons": result["reasons"],
        "evaluated_against": "artifacts/models/cross_domain_bundle.joblib (frozen FEMTO model)",
    }
    return entry


def main() -> None:
    payload = {"cwru": build_cwru_entry()}
    OUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUT_PATH}")
    print(json.dumps(payload["cwru"].get("applicability"), indent=2))


if __name__ == "__main__":
    main()
