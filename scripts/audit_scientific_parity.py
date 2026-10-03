#!/usr/bin/env python
"""Scientific release audit: served raw-data path vs the trusted offline pipeline.

Executes, on committed real data only (deploy_data/ snapshot + data/fixtures/),
the checks reported in docs/scientific-parity.md and writes the measured numbers
to reports/verification/scientific-parity-evidence.json. Requires the mounted
artifacts/models/ binaries listed in artifacts/models/manifest.json.

Nothing here fits, tunes or selects anything: every model is loaded as-is.

Usage:
    python scripts/audit_scientific_parity.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from bearing_pdm import api  # noqa: E402
from bearing_pdm.chunked import WindowReport, iter_csv_window_features  # noqa: E402
from bearing_pdm.health import apply_reference_hi  # noqa: E402
from bearing_pdm.modeling import predict_tree_baseline  # noqa: E402
from bearing_pdm.stages import assign_stages  # noqa: E402

DEPLOY = ROOT / "deploy_data"
MODELS = ROOT / "artifacts" / "models"
OUT = ROOT / "reports" / "verification" / "scientific-parity-evidence.json"
FEMTO_FIXTURE = ROOT / "data" / "fixtures" / "femto" / "Bearing1_1"
WINDOW = api.FEMTO_ACQUISITION_SAMPLES
RATE = api.FEMTO_SAMPLE_RATE_HZ
CHUNK_SIZES = (1, 7, 997, WINDOW - 1, WINDOW, WINDOW + 1, 4096, 65_536)
AXES = ("vibration_x", "vibration_y")


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _max_diff(a: dict[str, float], b: dict[str, float]) -> tuple[float, float]:
    keys = sorted(a)
    x = np.array([a[k] for k in keys], dtype=float)
    y = np.array([b[k] for k in keys], dtype=float)
    abs_diff = np.abs(x - y)
    rel = abs_diff / np.maximum(np.abs(y), 1e-300)
    return float(abs_diff.max()), float(rel.max())


def _csv(frame: pd.DataFrame) -> bytes:
    # repr-precision floats: the CSV round-trips every float64 sample exactly.
    return frame.to_csv(index=False, float_format="%.17g").encode()


def recorded_samples(values) -> np.ndarray:
    """deploy_data stores raw samples as float32 to stay small. FEMTO records
    3-decimal text, so the shortest float32 repr is that text; parsing it back
    gives exactly the float64 the offline reader produced from the CSV."""
    return np.asarray(values, dtype=np.float32).astype(str).astype(np.float64)


def snapshot_and_raw():
    snapshot = pd.read_parquet(DEPLOY / "feature_snapshot.parquet")
    raw = pd.read_parquet(DEPLOY / "raw_signal_samples.parquet")
    raw = raw[raw.dataset_id == "femto"].reset_index(drop=True)
    for axis in AXES:
        raw[axis] = raw[axis].map(recorded_samples)
    return snapshot, raw


def chunked_vs_reference(snapshot, raw) -> dict:
    """Every real FEMTO raw acquisition, concatenated per bearing, through the
    bounded-memory extractor at chunk sizes that do and do not divide 2560."""
    worst_abs = worst_rel = 0.0
    accounting = []
    with tempfile.TemporaryDirectory() as tmp:
        for bearing, group in raw.groupby("bearing_run_id", sort=True):
            group = group.sort_values("sequence_index")
            frame = pd.DataFrame({axis: np.concatenate(group[axis].to_numpy()) for axis in AXES})
            path = Path(tmp) / "run.csv"
            path.write_bytes(_csv(frame))
            reference = snapshot.set_index(["bearing_run_id", "sequence_index"])
            for chunk_rows in CHUNK_SIZES:
                for axis in AXES:
                    report = WindowReport()
                    windows = list(iter_csv_window_features(
                        path, vibration_column=axis, window_samples=WINDOW, overlap_samples=0,
                        chunk_rows=chunk_rows, sample_rate_hz=RATE, report=report))
                    accounting.append({
                        "bearing": bearing, "chunk_rows": chunk_rows, "axis": axis,
                        "rows_in_file": len(frame), "rows_read": report.rows_read,
                        "windows": len(windows), "trailing_partial_rows": report.trailing_partial_rows,
                        "rows_covered": sum(w.row_stop - w.row_start for w in windows),
                    })
                    for window, seq in zip(windows, group["sequence_index"], strict=True):
                        expected = {k: float(v) for k, v in reference.loc[(bearing, seq)].items()
                                    if k.startswith(axis + "_") and k in window.features}
                        assert window.features.keys() == expected.keys()
                        a, r = _max_diff(window.features, expected)
                        worst_abs, worst_rel = max(worst_abs, a), max(worst_rel, r)
    return {"acquisitions": int(len(raw)), "bearings": sorted(raw.bearing_run_id.unique()),
            "chunk_sizes": list(CHUNK_SIZES), "max_abs_diff": worst_abs, "max_rel_diff": worst_rel,
            "row_accounting_ok": all(
                a["rows_read"] == a["rows_in_file"] == a["rows_covered"] + a["trailing_partial_rows"]
                and a["trailing_partial_rows"] == 0 for a in accounting),
            "runs_checked": len(accounting)}


def api_rul_vs_offline(snapshot, raw, tree, client) -> dict:
    """/analyze/rul (chunked, two axes, gates, HI, RUL) on the concatenated real
    acquisitions of each bearing vs predict_tree_baseline on the snapshot row."""
    results = []
    for bearing, group in raw.groupby("bearing_run_id", sort=True):
        group = group.sort_values("sequence_index")
        frame = pd.DataFrame({axis: np.concatenate(group[axis].to_numpy()) for axis in AXES})
        last = snapshot[(snapshot.bearing_run_id == bearing)
                        & (snapshot.sequence_index == group.sequence_index.iloc[-1])]
        offline = float(predict_tree_baseline(last, tree).iloc[0])
        response = client.post("/analyze/rul", params={
            "dataset_id": "femto", "units": "g", "sampling_rate_hz": RATE,
            "preprocessing_version": api.FEMTO_PREPROCESSING_VERSION,
        }, files={"file": ("run.csv", _csv(frame), "text/csv")})
        body = response.json()
        results.append({
            "bearing": bearing, "acquisitions": int(len(group)), "status": response.status_code,
            "offline_rul_seconds": offline, "served_rul_seconds": body.get("rul_seconds"),
            "abs_diff_seconds": abs(offline - body["rul_seconds"]) if response.is_success else None,
            "applicability_level": body.get("applicability_level"),
            "compatibility": body.get("compatibility"),
        })
    return {"runs": results}


def artifact_parity(snapshot, tree) -> dict:
    manifest = json.loads((MODELS / "manifest.json").read_text())["artifacts"]
    checksums = {name: _sha256(MODELS / name) == entry["sha256"] for name, entry in manifest.items()}
    femto = snapshot[snapshot.dataset_id == "femto"]
    served = api._load_joblib("rul_extra_trees.joblib")
    direct = predict_tree_baseline(femto, tree).to_numpy()
    x = femto[list(served.feature_columns)].fillna(served.median_fill)
    via_served = served.model.predict(x)
    in_sample = np.abs(direct - femto["rul_seconds"].to_numpy())
    return {
        "manifest_checksums_match": checksums,
        "rows": int(len(femto)),
        "served_vs_direct_max_abs_diff_seconds": float(np.abs(direct - via_served).max()),
        "in_sample_abs_error_seconds_max": float(in_sample.max()),
        "in_sample_note": "Training rows (in-sample): identity check of the artifact, not accuracy.",
        "deploy_data_copies_identical": {
            name: _sha256(DEPLOY / name) == _sha256(MODELS / name)
            for name in ("reference_hi_model.joblib", "stage_thresholds.joblib",
                         "rul_naive.joblib", "rul_selected_model.json")},
    }


def hi_parity(snapshot, client) -> dict:
    hi_model = joblib.load(MODELS / "reference_hi_model.joblib")
    thresholds = joblib.load(MODELS / "stage_thresholds.joblib")
    results = []
    for bearing, group in snapshot[snapshot.dataset_id == "femto"].groupby("bearing_run_id"):
        group = group.sort_values("sequence_index").reset_index(drop=True)
        offline_hi = apply_reference_hi(group, hi_model)
        offline_stage = assign_stages(group, offline_hi, thresholds)
        rows = [{**{c: float(r[c]) for c in hi_model.features},
                 "sequence_index": int(r.sequence_index)} for _, r in group.iterrows()]
        # Shuffled on purpose: the served path must restore temporal order itself.
        rng = np.random.default_rng(0)
        rows = [rows[i] for i in rng.permutation(len(rows))]
        response = client.post("/predict/hi", json={"dataset_id": "femto", "rows": rows})
        served = sorted(response.json()["rows"], key=lambda r: r["sequence_index"])
        results.append({
            "bearing": bearing, "rows": int(len(group)), "status": response.status_code,
            "max_abs_hi_diff": float(np.abs(np.array([r["health_indicator"] for r in served])
                                            - offline_hi.to_numpy()).max()),
            "stages_identical": [r["stage"] for r in served] == offline_stage.tolist(),
        })
    return {"runs": results}


def applicability_on_real_data(snapshot, client) -> dict:
    """Training-domain rows vs a real out-of-domain recording (college rig),
    scored through /predict/rul's own gate."""
    out = {}
    femto = snapshot[snapshot.dataset_id == "femto"]
    for bearing, group in femto.groupby("bearing_run_id"):
        row = group.sort_values("sequence_index").iloc[-1]
        features = {c: float(row[c]) for c in snapshot.columns if c.startswith(AXES)
                    and np.isfinite(row[c])}
        response = client.post("/predict/rul", json={"dataset_id": "femto", "features": features})
        out[bearing] = {"status": response.status_code,
                        "level": response.json().get("applicability_level"),
                        "code": response.json().get("code")}
    # Per-recording levels over every snapshot acquisition, batched. Identical
    # to /predict/rul's single-row assessment: one distance, no missing
    # features, no metadata columns in the served feature row.
    from bearing_pdm.applicability import _level, recording_distances
    from bearing_pdm.routing import candidates_from_bundle

    model = next(c for c in candidates_from_bundle(api._load_bundle())
                 if c.name == "raw_seconds").applicability
    levels = {}
    for bearing, group in femto.groupby("bearing_run_id"):
        group = group.sort_values("sequence_index")
        level = pd.Series(_level(recording_distances(group, model) / model.in_domain_distance))
        last = level.iloc[int(0.9 * len(level)):]
        levels[bearing] = {"all": level.value_counts().to_dict(),
                           "last_10pct_of_life": last.value_counts().to_dict()}
    out["per_recording_levels_training_bearings"] = levels
    college = pd.read_parquet(DEPLOY / "raw_signal_samples.parquet")
    college = college[college.dataset_id == "college"]
    from bearing_pdm.features import frequency_domain_features, time_domain_features
    for _, rec in college.iterrows():
        features = {}
        for axis in AXES:
            # One FEMTO-length window at the college rig's own recorded rate: the
            # question is only whether the gate recognises it as out of domain.
            signal = np.asarray(rec[axis], dtype=float)[:WINDOW]
            features.update(time_domain_features(signal, axis))
            features.update(frequency_domain_features(signal, float(rec.sample_rate_hz), axis))
        response = client.post("/predict/rul", json={"dataset_id": "femto", "features": features})
        body = response.json()
        out[f"{rec.bearing_run_id}#{rec.sequence_index}"] = {
            "status": response.status_code, "code": body.get("code"),
            "rul_seconds": body.get("rul_seconds"), "sample_rate_hz": float(rec.sample_rate_hz),
            "level": body.get("applicability_level"), "compatibility": body.get("compatibility")}
    return out


def leakage_spy(client) -> dict:
    """Count every sklearn fit/partial_fit/fit_transform reached during one full
    /analyze/rul request and record what data each one saw."""
    from sklearn.base import BaseEstimator

    seen = []
    patched = []
    for cls in _all_subclasses(BaseEstimator):
        for attr in ("fit", "partial_fit", "fit_transform", "fit_predict"):
            original = cls.__dict__.get(attr)
            if original is None:
                continue

            def spy(self, *args, _original=original, _name=f"{cls.__name__}.{attr}", **kwargs):
                seen.append({"call": _name, "rows": int(len(args[0])) if args else None})
                return _original(self, *args, **kwargs)

            setattr(cls, attr, spy)
            patched.append((cls, attr, original))
    try:
        bundle = api._load_bundle()
        candidate = next(c for c in __import__("bearing_pdm.routing", fromlist=["x"])
                         .candidates_from_bundle(bundle) if c.name == "raw_seconds")
        before = candidate.applicability.reference.copy()
        frame = pd.concat(
            [pd.read_csv(FEMTO_FIXTURE / f"acc_0000{i}.csv", header=None)[[4, 5]] for i in (1, 2)])
        frame.columns = list(AXES)
        response = client.post("/analyze/rul", params={
            "dataset_id": "femto", "units": "g", "sampling_rate_hz": RATE,
            "preprocessing_version": api.FEMTO_PREPROCESSING_VERSION,
        }, files={"file": ("run.csv", frame.to_csv(index=False).encode(), "text/csv")})
        unchanged = bool(np.array_equal(before, candidate.applicability.reference))
    finally:
        for cls, attr, original in patched:
            setattr(cls, attr, original)
    return {"status": response.status_code, "fit_calls": seen,
            "reference_rows": int(len(before)), "applicability_reference_unchanged": unchanged}


def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


def main() -> None:
    snapshot, raw = snapshot_and_raw()
    tree = joblib.load(MODELS / "rul_extra_trees.joblib")
    with TestClient(api.app) as client:
        evidence = {
            "chunked_vs_reference_features": chunked_vs_reference(snapshot, raw),
            "analyze_rul_vs_offline": api_rul_vs_offline(snapshot, raw, tree, client),
            "artifact_parity": artifact_parity(snapshot, tree),
            "hi_parity": hi_parity(snapshot, client),
            "applicability_real_data": applicability_on_real_data(snapshot, client),
            "leakage_spy": leakage_spy(client),
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2, default=str) + "\n")
    print(json.dumps(evidence, indent=2, default=str))


if __name__ == "__main__":
    main()
