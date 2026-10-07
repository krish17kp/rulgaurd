"""Content-addressed disk cache for expensive, deterministic analysis (nightshift Phase V).

Key = sha256(raw_input_bytes) + a caller-supplied version string (adapter/feature-schema/
config version). Same input + same version -> cache hit, byte-identical result. Any science
change must bump its version string so stale JSON is never served.

Deliberately NOT a general caching framework: one directory, one JSON file per key, no TTL,
no eviction. Good enough for the few genuinely expensive operations added in Phases D-N
(bearing-ZIP analysis, knowledge-bundle ingestion); callers wrap their own compute function.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cache_dir() -> Path:
    configured = os.environ.get("BEARING_PDM_COMPUTE_CACHE_DIR")
    cache = Path(configured) if configured else REPO_ROOT / ".cache" / "compute"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def cache_key(raw_input: bytes, version: str) -> str:
    """sha256(raw_input) salted with `version` - changing version always changes the key."""
    digest = hashlib.sha256(raw_input)
    digest.update(b"\0")
    digest.update(version.encode("utf-8"))
    return digest.hexdigest()


def cached_json_call(
    raw_input: bytes,
    version: str,
    compute: Callable[[], Any],
    to_json: Callable[[Any], dict],
    from_json: Callable[[dict], Any],
) -> Any:
    """Return `compute()`'s result, serving a cache hit when input+version match a prior call.

    `to_json`/`from_json` convert the result to/from a JSON-safe dict (e.g.
    `dataclasses.asdict` / `MyDataclass(**d)`), so the cache stays human-inspectable JSON
    rather than an opaque/untrusted pickle.
    """
    key = cache_key(raw_input, version)
    path = _cache_dir() / f"{key}.json"
    if path.exists():
        return from_json(json.loads(path.read_text()))

    result = compute()
    payload = to_json(result)
    # Atomic write: a crash mid-write must never leave a corrupt cache entry.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return result


def demo() -> None:
    calls = []

    def compute():
        calls.append(1)
        return {"n": 42}

    r1 = cached_json_call(b"abc", "v1", compute, lambda x: x, lambda d: d)
    r2 = cached_json_call(b"abc", "v1", compute, lambda x: x, lambda d: d)
    assert r1 == r2 == {"n": 42}
    assert len(calls) == 1, "second call with identical input+version must hit the cache"

    cached_json_call(b"abc", "v2", compute, lambda x: x, lambda d: d)
    assert len(calls) == 2, "version bump must force recomputation"

    cached_json_call(b"xyz", "v1", compute, lambda x: x, lambda d: d)
    assert len(calls) == 3, "different input must force recomputation"
    print("compute_cache.demo() OK")


if __name__ == "__main__":
    demo()
