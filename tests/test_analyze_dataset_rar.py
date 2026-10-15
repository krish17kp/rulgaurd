from __future__ import annotations

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
