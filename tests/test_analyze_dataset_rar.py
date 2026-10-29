from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_dataset  # noqa: E402


def test_resolve_root_passes_through_plain_folder(tmp_path):
    folder = tmp_path / "already_extracted"
    folder.mkdir()
    (folder / "data.csv").write_text("x")
    assert analyze_dataset._resolve_root(folder) == folder


def test_resolve_root_extracts_rar_and_unwraps_single_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze_dataset, "RAR_SCRATCH_ROOT", tmp_path / "scratch")
    root = tmp_path / "download"
    root.mkdir()
    (root / "set.part01.rar").write_bytes(b"fake")

    calls = []

    def fake_extract(rar_file, dest):
        calls.append(dest)
        wrapper = Path(dest) / "XJTU-SY_Bearing_Datasets"
        (wrapper / "35Hz12kN").mkdir(parents=True)
        (wrapper / "37.5Hz11kN").mkdir(parents=True)
        return ["XJTU-SY_Bearing_Datasets/35Hz12kN", "XJTU-SY_Bearing_Datasets/37.5Hz11kN"]

    monkeypatch.setattr(analyze_dataset, "safe_extract_rar", fake_extract)
    resolved = analyze_dataset._resolve_root(root)
    assert resolved.name == "XJTU-SY_Bearing_Datasets"
    assert (resolved / "35Hz12kN").is_dir()
    assert len(calls) == 1

    # Second call with the identical archive identity reuses the extraction
    # instead of calling safe_extract_rar (and its unrar subprocess) again.
    resolved_again = analyze_dataset._resolve_root(root)
    assert resolved_again == resolved
    assert len(calls) == 1


def test_resolve_root_accepts_rar_file_directly(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze_dataset, "RAR_SCRATCH_ROOT", tmp_path / "scratch")
    rar_file = tmp_path / "single.rar"
    rar_file.write_bytes(b"fake")

    def fake_extract(path, dest):
        (Path(dest) / "data.csv").write_text("x")
        return ["data.csv"]

    monkeypatch.setattr(analyze_dataset, "safe_extract_rar", fake_extract)
    resolved = analyze_dataset._resolve_root(rar_file)
    assert (resolved / "data.csv").exists()


def test_run_analysis_persists_canonical_parquet_and_manifest(tmp_path, monkeypatch):
    """A real gap: run_analysis computed canonical features on a cache miss but never
    wrote them, so routing_<dataset>.json's canonical_path was always null and the
    dashboard's Signal/Features tabs couldn't find a source. Covers the fix."""
    from dataclasses import dataclass

    import pandas as pd

    @dataclass
    class FakeThresholds:
        persistence: int = 1

    monkeypatch.chdir(tmp_path)

    class FakeRun:
        run_id = "xjtu:Bearing1_1"

    class FakeAdapter:
        display_name = "XJTU-SY bearing run-to-failure (Xi'an Jiaotong Univ.)"
        reference_window = (2, 10)

        def discover(self, root, role=None):
            return [FakeRun()]

    fake_df = pd.DataFrame({
        "bearing_run_id": ["xjtu:Bearing1_1", "xjtu:Bearing1_1"],
        "sequence_index": [0, 1],
        "elapsed_s": [0.0, 60.0],
        "vibration_x_rms": [0.1, 0.2],
    })

    monkeypatch.setattr(analyze_dataset, "profile_folder", lambda root: {
        "n_files": 2, "sampling_rate_hz": 25600.0, "sampling_rate_source": "test fixture",
        "channels_found": ["vibration_x"], "known_datasets": [{"dataset_id": "xjtu"}],
        "warnings": [], "files": [],
    })
    monkeypatch.setattr(analyze_dataset, "get_adapter", lambda dataset: FakeAdapter())
    monkeypatch.setattr(analyze_dataset, "build_canonical_features", lambda adapter, run: fake_df)
    import bearing_pdm.domain as domain
    import bearing_pdm.routing as routing

    monkeypatch.setattr(domain, "add_self_normalized_features", lambda df: df)
    monkeypatch.setattr(analyze_dataset.joblib, "load", lambda path: {
        "stage_thresholds": FakeThresholds(),
        "hi_model": object(),
    })
    monkeypatch.setattr(routing, "candidates_from_bundle", lambda bundle: [])
    monkeypatch.setattr(analyze_dataset, "oof_from_predictions", lambda preds: None)
    monkeypatch.setattr(domain, "stage_persistence", lambda dataset: 1)
    monkeypatch.setattr(domain, "reference_window", lambda dataset: (2, 10))
    monkeypatch.setattr(domain, "hi_smooth_window", lambda dataset: 1)

    def fake_analyze_bearing(g, candidates, hi_model, thresholds, ref_window, oof=None,
                             smooth_window=None):
        out = g.copy()
        out["health_indicator"] = 0.9
        out["stage"] = "HEALTHY"
        out["actual_rul_seconds"] = None
        out["rul_status"] = "RUL_SUPPRESSED"
        out["predicted_rul_seconds"] = None
        out["rul_lo"] = None
        out["rul_hi"] = None
        decision = {"status": "RUL_SUPPRESSED", "quality_ok": True, "quality_reasons": [],
                    "current": {"status": "RUL_SUPPRESSED", "model": None},
                    "applicability": {}}
        return out, decision

    monkeypatch.setattr(routing, "analyze_bearing", fake_analyze_bearing)

    root = tmp_path / "source"
    root.mkdir()
    dataset = analyze_dataset.run_analysis(root, dataset="xjtu")

    assert dataset == "xjtu"
    cached = tmp_path / "data" / "processed" / "canonical_xjtu.parquet"
    manifest_path = cached.with_suffix(".json")
    assert cached.exists(), "canonical parquet must be persisted on a cache miss"
    assert manifest_path.exists(), "canonical manifest must be written alongside it"

    manifest = json.loads(manifest_path.read_text())
    for key in ("dataset_id", "display_name", "role", "source_root", "n_rows", "bearings",
                "window_s", "schema_version", "reference_window", "code_version", "created_at"):
        assert key in manifest, f"manifest missing {key!r}"
    assert manifest["dataset_id"] == "xjtu"
    assert manifest["source_root"] == str(root), (
        "source_root must point at the real (persistent) resolved root, not a vanished tmp dir"
    )

    routing = json.loads((tmp_path / "reports" / "metrics" / "routing_xjtu.json").read_text())
    assert routing["canonical_path"] == str(Path("data/processed/canonical_xjtu.parquet")), (
        "routing_<dataset>.json must carry the real canonical_path, not null"
    )
