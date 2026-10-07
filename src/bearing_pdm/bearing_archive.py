"""Whole-bearing FEMTO ZIP analysis (nightshift Phase F).

Wires archive.py's secure ZIP primitives into the existing scientific pipeline
(femto.py adapter, pipeline.py feature rows, health.py/stages.py fitted
artifacts) so a user-supplied `Bearing2_1.zip` of acc_*/temp_* files gets the
same per-acquisition features, HI and stage as the canonical offline dataset -
computed fresh from the uploaded files, never fabricated or recomputed with
different formulas.

Held-out predicted RUL is NOT recomputed here (that would require retraining
or an in-sample substitute for a held-out prediction, both forbidden by
ml-data.md). It is looked up from the already-committed leave-one-bearing-out
artifact (deploy_data/trajectory_data.json) by bearing_run_id, exactly as the
`/trajectory` endpoint already does - if the uploaded bearing isn't one of the
6 learning bearings with a committed held-out prediction, that field is None
with an explicit reason, never guessed.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from bearing_pdm.archive import (
    LOCAL_FULL_MODE,
    DatasetArchiveManifest,
    ZipLimits,
    ZipSecurityError,
    build_manifest_from_zip,
    safe_extract_zip,
)
from bearing_pdm.femto import FemtoBearing, list_acquisition_indices, read_acceleration
from bearing_pdm.pipeline import build_femto_feature_rows, sha256_file
from bearing_pdm.stages import assign_stages

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DATA_DIR = REPO_ROOT / "deploy_data"

FEMTO_SAMPLE_RATE_HZ = 25_600.0
_BEARING_DIR_RE = re.compile(r"^Bearing(\d+)_(\d+)$", re.IGNORECASE)


class BearingArchiveError(ValueError):
    """Raised when an uploaded archive cannot be analyzed as a FEMTO bearing."""


@dataclass(frozen=True)
class BearingAnalysis:
    manifest: DatasetArchiveManifest
    bearing_run_id: str
    acquisition_count: int
    sample_rate_hz: float
    representative_indices: dict[str, int]  # {"early": N, "middle": N, "late": N}
    representative_signals: dict[str, dict[str, list[float]]]
    representative_fft: dict[str, dict[str, list[float]]]
    feature_trajectory: dict[str, list[float]]  # feature name -> per-acquisition values
    sequence_index: list[int]
    reference_hi: list[float] | None
    transparent_hi: list[float] | None
    pca_hi: list[float] | None
    stage: list[str] | None
    actual_rul_seconds: list[float | None]
    held_out_predicted_rul_seconds: list[float] | None
    held_out_mae_seconds: float | None
    held_out_unavailable_reason: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _load_joblib(path: Path):
    import joblib

    return joblib.load(path) if path.exists() else None


def _find_bearing_dir(extracted_root: Path, bearing_label: str) -> Path:
    for p in extracted_root.rglob(bearing_label):
        if p.is_dir():
            return p
    # Flat ZIP (no bearing-named folder): files extracted directly at root.
    if any(extracted_root.glob("acc_*.csv")):
        return extracted_root
    raise BearingArchiveError(f"could not locate a {bearing_label!r} folder in the extracted archive")


def _representative_fft(signal: np.ndarray, sample_rate_hz: float) -> dict[str, list[float]]:
    freqs = np.fft.rfftfreq(signal.size, d=1.0 / sample_rate_hz)
    magnitude = np.abs(np.fft.rfft(signal))
    return {
        "frequency_hz": [float(v) for v in freqs],
        "magnitude": [float(v) for v in magnitude],
    }


def analyze_femto_bearing_zip(
    zip_path: str | Path, limits: ZipLimits = LOCAL_FULL_MODE
) -> BearingAnalysis:
    """Validate, extract, and run the existing FEMTO pipeline over one bearing ZIP."""
    zip_path = Path(zip_path)
    source_sha256 = sha256_file(zip_path)
    manifest = build_manifest_from_zip(zip_path, sha256=source_sha256)

    if manifest.compatibility == "INVALID_ARCHIVE":
        raise BearingArchiveError(f"invalid archive: {manifest.warnings}")
    if manifest.dataset_type != "femto_bearing":
        raise BearingArchiveError(
            f"not a FEMTO bearing archive (detected dataset_type={manifest.dataset_type!r}); "
            "expected a single BearingC_N folder of acc_*.csv/temp_*.csv files"
        )
    if len(manifest.bearing_run_ids) != 1:
        raise BearingArchiveError(
            f"expected exactly one bearing folder, found {manifest.bearing_run_ids!r} - "
            "a bearing ZIP must contain one bearing's acquisitions only"
        )
    bearing_label = manifest.bearing_run_ids[0]
    m = _BEARING_DIR_RE.match(bearing_label)
    if not m:
        raise BearingArchiveError(f"folder name {bearing_label!r} does not match BearingC_N")
    condition_id = int(m.group(1))

    with tempfile.TemporaryDirectory(prefix="rulguard_bearing_zip_") as tmp:
        dest = Path(tmp)
        try:
            safe_extract_zip(zip_path, dest, limits)
        except ZipSecurityError:
            raise  # propagate unchanged - callers must not swallow this

        bearing_dir = _find_bearing_dir(dest, bearing_label)
        acc_indices = list_acquisition_indices(bearing_dir)
        if not acc_indices:
            raise BearingArchiveError(f"no acc_*.csv files found under {bearing_label}")

        bearing = FemtoBearing(
            bearing_label=bearing_label, condition_id=condition_id, role="learning", path=bearing_dir
        )
        rows = list(build_femto_feature_rows(bearing, code_version="bearing_archive-v1"))
        df = pd.DataFrame(rows).sort_values("sequence_index").reset_index(drop=True)

        # Representative early/middle/late raw signal + FFT - real uploaded samples only.
        rep_positions = {
            "early": acc_indices[0],
            "middle": acc_indices[len(acc_indices) // 2],
            "late": acc_indices[-1],
        }
        rep_signals: dict[str, dict[str, list[float]]] = {}
        rep_fft: dict[str, dict[str, list[float]]] = {}
        for label, acc_idx in rep_positions.items():
            acc_df = read_acceleration(bearing_dir, acc_idx)
            x = acc_df["accel_horizontal"].to_numpy()
            y = acc_df["accel_vertical"].to_numpy()
            rep_signals[label] = {
                "vibration_x": [float(v) for v in x],
                "vibration_y": [float(v) for v in y],
            }
            rep_fft[label] = {
                "vibration_x": _representative_fft(x, FEMTO_SAMPLE_RATE_HZ),
                "vibration_y": _representative_fft(y, FEMTO_SAMPLE_RATE_HZ),
            }

        feature_cols = [
            c for c in df.columns
            if c not in (
                "acquisition_id", "dataset_id", "bearing_run_id", "role", "source_file_path",
                "sequence_index", "event_timestamp", "sample_rate_hz", "n_samples", "row_start",
                "row_end", "schema_version", "source_sha256", "code_version", "temp_available",
                "rul_seconds", "stage_label",
            )
        ]
        feature_trajectory = {c: [None if pd.isna(v) else float(v) for v in df[c]] for c in feature_cols}

        bearing_run_id = f"femto:{bearing_label}"

        reference_model = _load_joblib(DEPLOY_DATA_DIR / "reference_hi_model.joblib")
        thresholds = _load_joblib(DEPLOY_DATA_DIR / "stage_thresholds.joblib")
        transparent_baseline = _load_joblib(DEPLOY_DATA_DIR / "transparent_hi_baseline.joblib")
        pca_model = _load_joblib(DEPLOY_DATA_DIR / "pca_hi_model.joblib")

        reference_hi = transparent_hi = pca_hi = stage = None
        warnings: list[str] = []
        if reference_model is not None and thresholds is not None:
            from bearing_pdm.health import apply_pca_hi, apply_reference_hi, apply_transparent_hi

            hi_series = apply_reference_hi(df, reference_model)
            reference_hi = [round(float(v), 4) for v in hi_series]
            stage = assign_stages(df, hi_series, thresholds).tolist()
            if transparent_baseline is not None:
                transparent_hi = [round(float(v), 4) for v in apply_transparent_hi(df, transparent_baseline)]
            if pca_model is not None:
                pca_hi = [round(float(v), 4) for v in apply_pca_hi(df, pca_model)]
        else:
            warnings.append("reference_hi_model.joblib / stage_thresholds.joblib not found under deploy_data/ "
                             "- HI and stage are unavailable, not fabricated")

        actual_rul = [None if pd.isna(v) else round(float(v), 1) for v in df["rul_seconds"]]

        held_out_predicted = None
        held_out_mae = None
        held_out_reason = None
        trajectory_json_path = DEPLOY_DATA_DIR / "trajectory_data.json"
        if trajectory_json_path.exists():
            cached = json.loads(trajectory_json_path.read_text())
            entry = cached.get(bearing_run_id)
            if entry is not None:
                held_out_block = entry.get("held_out_predicted_rul_seconds")
                held_out_predicted = (
                    held_out_block.get("predicted_rul_seconds") if isinstance(held_out_block, dict) else None
                )
                held_out_mae = (
                    entry.get("held_out_metrics", {}).get("mae_seconds")
                    if isinstance(entry.get("held_out_metrics"), dict)
                    else None
                )
                if held_out_predicted is None and held_out_mae is None:
                    held_out_reason = (
                        f"{bearing_run_id} is present in the cached trajectory artifact but it "
                        "has no held-out predicted RUL field recorded"
                    )
            else:
                held_out_reason = (
                    f"{bearing_run_id} has no committed leave-one-bearing-out evaluation artifact "
                    "- this bearing was not part of the frozen FEMTO evaluation, so no held-out "
                    "prediction exists to display (never substituted with an in-sample prediction)"
                )
        else:
            held_out_reason = "deploy_data/trajectory_data.json not found - held-out RUL unavailable"

        return BearingAnalysis(
            manifest=manifest,
            bearing_run_id=bearing_run_id,
            acquisition_count=len(acc_indices),
            sample_rate_hz=FEMTO_SAMPLE_RATE_HZ,
            representative_indices=rep_positions,
            representative_signals=rep_signals,
            representative_fft=rep_fft,
            feature_trajectory=feature_trajectory,
            sequence_index=df["sequence_index"].astype(int).tolist(),
            reference_hi=reference_hi,
            transparent_hi=transparent_hi,
            pca_hi=pca_hi,
            stage=stage,
            actual_rul_seconds=actual_rul,
            held_out_predicted_rul_seconds=held_out_predicted,
            held_out_mae_seconds=held_out_mae,
            held_out_unavailable_reason=held_out_reason,
            warnings=tuple(warnings),
        )


def demo() -> None:
    """ponytail self-check: build a tiny synthetic-but-real-shaped bearing ZIP
    from two real Bearing2_1 acquisitions and confirm the pipeline runs end to
    end without retraining or fabricating HI/stage/feature values."""
    import zipfile

    source_dir = REPO_ROOT / "data/interim/femto/Learning_set/Bearing2_1"
    if not source_dir.is_dir():
        print("bearing_archive.py demo: skipped (Bearing2_1 learning-set folder not present locally)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "Bearing2_1.zip"
        acc_files = sorted(source_dir.glob("acc_*.csv"))[:5]
        with zipfile.ZipFile(zip_path, "w") as zf:
            for f in acc_files:
                zf.write(f, arcname=f"Bearing2_1/{f.name}")

        analysis = analyze_femto_bearing_zip(zip_path)
        assert analysis.bearing_run_id == "femto:Bearing2_1"
        assert analysis.acquisition_count == len(acc_files)
        assert analysis.sample_rate_hz == FEMTO_SAMPLE_RATE_HZ
        assert "early" in analysis.representative_signals
        assert len(analysis.representative_signals["early"]["vibration_x"]) == 2560
        assert "vibration_x_rms" in analysis.feature_trajectory
        assert len(analysis.feature_trajectory["vibration_x_rms"]) == len(acc_files)

    print("bearing_archive.py demo: all checks passed")


if __name__ == "__main__":
    demo()
