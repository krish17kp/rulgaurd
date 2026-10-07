"""Overwrite guard for artifacts/models/cross_domain_bundle.joblib.

run_cross_dataset.py must never replace the canonical bundle unless its
required inputs (currently: canonical_femto_learning.parquet - see the
module-level comment on REQUIRED_CANONICAL) are present and readable. These
tests exercise the guard in isolation, without running the real (expensive,
multi-dataset) pipeline: check_inputs_present() and atomic_dump() are the two
pieces of logic that make the guard work, and main() is checked end-to-end
with required inputs deliberately absent.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import joblib
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_cross_dataset.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_cross_dataset", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_cross_dataset"] = module
    spec.loader.exec_module(module)
    return module


RCD = _load_script()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_check_inputs_present_flags_missing_required(tmp_path):
    assert RCD.check_inputs_present(tmp_path) == ["canonical_femto_learning"]


def test_check_inputs_present_flags_unreadable_required(tmp_path):
    bad = tmp_path / "canonical_femto_learning.parquet"
    bad.write_bytes(b"not a parquet file")
    assert RCD.check_inputs_present(tmp_path) == ["canonical_femto_learning"]


def test_check_inputs_present_passes_when_readable(tmp_path):
    import pandas as pd
    good = tmp_path / "canonical_femto_learning.parquet"
    pd.DataFrame({"a": [1, 2]}).to_parquet(good)
    assert RCD.check_inputs_present(tmp_path) == []


def test_atomic_dump_replaces_target_on_success(tmp_path):
    target = tmp_path / "bundle.joblib"
    joblib.dump({"old": True}, target)
    RCD.atomic_dump({"new": True}, target)
    assert joblib.load(target) == {"new": True}
    assert list(tmp_path.iterdir()) == [target]        # no leftover temp files


def test_atomic_dump_leaves_target_untouched_on_bad_payload(tmp_path):
    target = tmp_path / "bundle.joblib"
    joblib.dump({"old": True}, target)
    before = _sha256(target)
    with pytest.raises(ValueError):
        RCD.atomic_dump({}, target)                    # empty dict fails validation
    assert _sha256(target) == before
    assert list(tmp_path.iterdir()) == [target]         # temp file cleaned up


def test_main_fails_closed_when_femto_missing_and_leaves_bundle_untouched(tmp_path, monkeypatch):
    """The regression this guard exists for: an incomplete-inputs run must not
    overwrite a byte-for-byte good existing bundle."""
    processed = tmp_path / "processed"
    processed.mkdir()
    # canonical_femto_learning deliberately absent; an unrelated optional
    # dataset present, matching the "some data, but not the required kind" case.
    import pandas as pd
    pd.DataFrame({"a": [1]}).to_parquet(processed / "canonical_ims.parquet")

    bundle_out = tmp_path / "artifacts" / "models" / "cross_domain_bundle.joblib"
    bundle_out.parent.mkdir(parents=True)
    joblib.dump({"existing": "canonical bundle"}, bundle_out)
    before = _sha256(bundle_out)

    monkeypatch.chdir(tmp_path)
    rc = RCD.main(["--processed-dir", str(processed), "--bundle-out", str(bundle_out)])

    assert rc == 1
    assert _sha256(bundle_out) == before
    assert joblib.load(bundle_out) == {"existing": "canonical bundle"}
