"""Phase U: CLI entry points for archive/bundle/knowledge-bundle/external-eval."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

_ENV = {**os.environ, "PYTHONPATH": "src"}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, env=_ENV,
    )


def test_all_four_scripts_have_working_help():
    for script in (
        "scripts/analyze_archive.py",
        "scripts/build_analysis_bundle.py",
        "scripts/build_knowledge_bundle.py",
        "scripts/evaluate_external_dataset.py",
    ):
        result = _run(script, "--help")
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout


def test_analyze_archive_classifies_real_zip():
    result = _run("scripts/analyze_archive.py", "datasets/femto/Training_set.zip")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dataset_type"] == "femto_bearing"


def test_build_analysis_bundle_from_real_bearing_zip(tmp_path: Path):
    zip_path = tmp_path / "Bearing2_1.zip"
    src_dir = Path("data/interim/femto/Learning_set/Bearing2_1")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in sorted(src_dir.glob("*.csv"))[:5]:  # small slice, fast test
            zf.write(f, arcname=f"Bearing2_1/{f.name}")

    out_path = tmp_path / "out.rulguard.zip"
    result = _run(
        "scripts/build_analysis_bundle.py",
        "--femto-zip", str(zip_path),
        "--output", str(out_path),
    )
    assert result.returncode == 0, result.stderr
    assert out_path.exists()


def test_build_knowledge_bundle_from_real_docs(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("Bearing degradation and health indicators.\n")
    out_path = tmp_path / "out.rulguard-knowledge.zip"
    result = _run(
        "scripts/build_knowledge_bundle.py",
        "--dir", str(docs),
        "--output", str(out_path),
    )
    assert result.returncode == 0, result.stderr
    assert out_path.exists()


def test_evaluate_external_dataset_refuses_without_real_data(tmp_path: Path):
    missing = tmp_path / "nonexistent"
    result = _run(
        "scripts/evaluate_external_dataset.py", "--dataset", "ims", "--data-dir", str(missing),
    )
    assert result.returncode == 1
    assert "IMS.zip" in result.stderr


def test_evaluate_external_dataset_refuses_to_guess_structure(tmp_path: Path):
    data_dir = tmp_path / "ims_data"
    data_dir.mkdir()
    (data_dir / "placeholder.txt").write_text("not real IMS data\n")
    result = _run(
        "scripts/evaluate_external_dataset.py", "--dataset", "ims", "--data-dir", str(data_dir),
    )
    assert result.returncode == 2
    assert "not implemented" in result.stderr
