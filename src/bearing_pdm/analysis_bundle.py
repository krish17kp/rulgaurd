"""Portable `.rulguard.zip` analysis bundles (Nightshift Phase J).

A bundle packages the compact *derived* results already produced by the
scientific pipeline (FEMTO bearing trajectories, the college whole-run
trajectory, evaluation snapshots) so they can be uploaded to Vercel without
shipping the raw dataset. It never recomputes or refits anything - it is a
checksummed, versioned container around JSON that already exists on disk
(`deploy_data/trajectory_data.json`, `deploy_data/college_trajectory.json`,
etc.) or around an in-memory analysis object such as
`bearing_archive.BearingAnalysis`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


class BundleValidationError(ValueError):
    """Raised when a `.rulguard.zip` is malformed or its checksum fails."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _to_jsonable(payload: Any) -> Any:
    if dataclasses.is_dataclass(payload) and not isinstance(payload, type):
        return dataclasses.asdict(payload)
    return payload


def build_bundle(dataset_id: str, payload: Any, out_path: str | Path) -> Path:
    """Write a `.rulguard.zip` containing `payload` under `dataset.json`.

    `payload` must already be the compact derived result (a dict, or a
    dataclass such as `BearingAnalysis`) - never raw sensor rows. No
    absolute local paths or secrets may appear in it; callers are
    responsible for passing only display-safe data (this module does not
    guess what is sensitive).
    """
    data = _to_jsonable(payload)
    dataset_bytes = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    checksum = _sha256_bytes(dataset_bytes)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": "rulguard.zip",
        "dataset_id": dataset_id,
        "dataset_sha256": checksum,
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
    checksums = {"dataset.json": checksum, "manifest.json": _sha256_bytes(manifest_bytes)}

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("dataset.json", dataset_bytes)
        zf.writestr("checksums.json", json.dumps(checksums, sort_keys=True).encode("utf-8"))
    return out_path


def load_bundle(path: str | Path) -> dict[str, Any]:
    """Read a `.rulguard.zip`, verify its checksums, and return `dataset.json`.

    Raises `BundleValidationError` if any required member is missing or a
    checksum does not match - never returns unverified data.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        required = {"manifest.json", "dataset.json", "checksums.json"}
        if not required.issubset(names):
            raise BundleValidationError(f"{path}: missing members {required - names}")

        manifest_bytes = zf.read("manifest.json")
        dataset_bytes = zf.read("dataset.json")
        checksums_bytes = zf.read("checksums.json")

        checksums = json.loads(checksums_bytes)
        if _sha256_bytes(manifest_bytes) != checksums.get("manifest.json"):
            raise BundleValidationError(f"{path}: manifest.json checksum mismatch")
        if _sha256_bytes(dataset_bytes) != checksums.get("dataset.json"):
            raise BundleValidationError(f"{path}: dataset.json checksum mismatch")

        manifest = json.loads(manifest_bytes)
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise BundleValidationError(
                f"{path}: unsupported schema_version {manifest.get('schema_version')!r}"
            )
        if manifest.get("dataset_sha256") != checksums["dataset.json"]:
            raise BundleValidationError(f"{path}: manifest/checksums dataset_sha256 disagree")

        return json.loads(dataset_bytes)


def demo() -> None:
    """Self-check: round-trip a small payload through build/load."""
    import tempfile

    payload = {"dataset_id": "femto:DemoBearing", "reference_hi": [1.0, 0.9, 0.5]}
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "demo.rulguard.zip"
        build_bundle("femto:DemoBearing", payload, bundle_path)
        loaded = load_bundle(bundle_path)
        assert loaded == payload, "round trip must be exact"

        # Tamper check: corrupting the dataset must be caught, not silently accepted.
        with zipfile.ZipFile(bundle_path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            checksums = json.loads(zf.read("checksums.json"))
        tampered_path = Path(tmp) / "tampered.rulguard.zip"
        with zipfile.ZipFile(tampered_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest).encode())
            zf.writestr("dataset.json", b'{"dataset_id": "tampered"}')
            zf.writestr("checksums.json", json.dumps(checksums).encode())
        try:
            load_bundle(tampered_path)
        except BundleValidationError:
            pass
        else:
            raise AssertionError("tampered bundle must fail validation")
    print("analysis_bundle self-check OK")


if __name__ == "__main__":
    demo()
