from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from bearing_pdm import bearing_archive
from bearing_pdm.compute_cache import cache_key, cached_json_call

REPO_ROOT = Path(__file__).resolve().parents[1]
BEARING2_1 = REPO_ROOT / "data/interim/femto/Learning_set/Bearing2_1"


def test_identical_input_and_version_is_a_cache_hit(tmp_path, monkeypatch):
    monkeypatch.setenv("BEARING_PDM_COMPUTE_CACHE_DIR", str(tmp_path))
    calls = []

    def compute():
        calls.append(1)
        return {"n": 42}

    r1 = cached_json_call(b"abc", "v1", compute, lambda x: x, lambda d: d)
    r2 = cached_json_call(b"abc", "v1", compute, lambda x: x, lambda d: d)
    assert r1 == r2 == {"n": 42}
    assert len(calls) == 1


def test_different_input_bytes_is_a_cache_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("BEARING_PDM_COMPUTE_CACHE_DIR", str(tmp_path))
    calls = []

    def compute():
        calls.append(1)
        return {"n": len(calls)}

    cached_json_call(b"abc", "v1", compute, lambda x: x, lambda d: d)
    cached_json_call(b"xyz", "v1", compute, lambda x: x, lambda d: d)
    assert len(calls) == 2


def test_version_bump_forces_recomputation_even_for_identical_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("BEARING_PDM_COMPUTE_CACHE_DIR", str(tmp_path))
    calls = []

    def compute():
        calls.append(1)
        return {"n": len(calls)}

    cached_json_call(b"abc", "v1", compute, lambda x: x, lambda d: d)
    cached_json_call(b"abc", "v2", compute, lambda x: x, lambda d: d)
    assert len(calls) == 2


def test_cache_key_is_deterministic_and_version_sensitive():
    assert cache_key(b"abc", "v1") == cache_key(b"abc", "v1")
    assert cache_key(b"abc", "v1") != cache_key(b"abc", "v2")
    assert cache_key(b"abc", "v1") != cache_key(b"abz", "v1")


@pytest.mark.skipif(not BEARING2_1.is_dir(), reason="Bearing2_1 learning-set folder not present locally")
def test_cached_bearing_zip_analysis_matches_uncached_and_hits_second_time(tmp_path, monkeypatch):
    """Caching must not change any computed scientific value, and a second call on the
    same ZIP bytes must not recompute."""
    monkeypatch.setenv("BEARING_PDM_COMPUTE_CACHE_DIR", str(tmp_path))

    zip_path = tmp_path / "Bearing2_1.zip"
    acc_files = sorted(BEARING2_1.glob("acc_*.csv"))[:5]
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in acc_files:
            zf.write(f, arcname=f"Bearing2_1/{f.name}")

    uncached = bearing_archive.analyze_femto_bearing_zip(zip_path)

    calls = []
    real_analyze = bearing_archive.analyze_femto_bearing_zip

    def spy(*args, **kwargs):
        calls.append(1)
        return real_analyze(*args, **kwargs)

    monkeypatch.setattr(bearing_archive, "analyze_femto_bearing_zip", spy)

    first = bearing_archive.analyze_femto_bearing_zip_cached(zip_path)
    assert len(calls) == 1
    second = bearing_archive.analyze_femto_bearing_zip_cached(zip_path)
    assert len(calls) == 1, "second call on identical ZIP bytes must hit the cache"

    assert first == second == uncached
