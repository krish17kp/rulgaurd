"""Phase H: read-only FEMTO explorer never fits, correctly labels roles."""

from __future__ import annotations

import os
import subprocess
import sys

_ENV = {**os.environ, "PYTHONPATH": "src"}


def test_inspect_learning_set_lists_all_six_bearings():
    out = subprocess.run(
        [sys.executable, "scripts/inspect_femto_dataset.py", "data/interim/femto/Learning_set"],
        capture_output=True, text=True, check=True, env=_ENV,
    ).stdout
    assert "role: learning" in out
    for b in ("Bearing1_1", "Bearing1_2", "Bearing2_1", "Bearing2_2", "Bearing3_1", "Bearing3_2"):
        assert b in out


def test_inspect_full_test_set_warns_frozen():
    out = subprocess.run(
        [sys.executable, "scripts/inspect_femto_dataset.py", "data/interim/femto/Full_Test_Set"],
        capture_output=True, text=True, check=True, env=_ENV,
    ).stdout
    assert "role: full_test" in out
    assert "FROZEN EVALUATION ONLY" in out


def test_inspect_zip_reports_manifest():
    out = subprocess.run(
        [sys.executable, "scripts/inspect_femto_dataset.py", "datasets/femto/Training_set.zip"],
        capture_output=True, text=True, check=True, env=_ENV,
    ).stdout
    assert "dataset_type: femto_bearing" in out
