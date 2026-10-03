"""Production artifact delivery: locate, fetch, and checksum-verify trained
joblib artifacts without ever committing them to Git (security.md/git.md:
never commit artifacts/models/*).

docs/vercel-deployment.md's known blocker: a real Vercel deployment builds
from the Git repository, which never contains these binaries. This module
is the structural fix - a committed manifest.json (checksums/sizes only,
no binary content) plus a fetch-and-verify loader that downloads a missing
artifact from its declared source_url into a writable cache directory at
cold start, and refuses to use anything that doesn't match its recorded
sha256 (ml-data.md: a wrong number that looks right is worse than no
number - a corrupted/tampered/wrong-version artifact must never be
silently loaded).

This module never fits/trains a model (python.md's module-boundary rule) -
it only locates bytes and verifies them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("bearing_pdm.artifacts")

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "artifacts" / "models"
MANIFEST_PATH = MODELS_DIR / "manifest.json"

# Same bounded-memory chunked-download pattern as api.py's upload handling
# (python.md: "all raw reads are chunked") - a 200MB+ artifact must never
# be buffered whole in memory.
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
# Generous but finite - the largest current artifact (cross_domain_bundle.joblib)
# is ~220MB; this is a stated cap, never an unbounded accept. Counts bytes
# actually received, not a caller-supplied/possibly-absent Content-Length.
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024

# Serializes concurrent ensure_artifact(name) calls for the SAME name within
# one process (FastAPI's sync `def` endpoints run in a thread pool, so two
# requests can genuinely race here) - review found that without this, two
# threads downloading the same missing artifact could interleave writes to
# one shared temp file and end up loading bytes that were never checksummed
# as a whole. This does not protect against two separate OS processes (e.g.
# two serverless instances) racing the same cache path - a per-download
# unique temp file + atomic rename (below) keeps that case safe too, just
# with wasted duplicate downloads rather than a corrupted file.
_download_locks: dict[str, threading.Lock] = {}
_download_locks_guard = threading.Lock()


def _lock_for(name: str) -> threading.Lock:
    with _download_locks_guard:
        return _download_locks.setdefault(name, threading.Lock())


def _cache_dir() -> Path:
    """Where a fetched artifact is cached for this process's lifetime.
    ARTIFACT_CACHE_DIR lets a deployment point this at a writable,
    persistent-enough location (e.g. Vercel's /tmp survives within one
    warm Fluid Compute instance); defaults to the system tempdir."""
    configured = os.environ.get("ARTIFACT_CACHE_DIR")
    cache = Path(configured) if configured else Path(tempfile.gettempdir()) / "bearing_pdm_artifacts"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def load_manifest() -> dict[str, dict[str, Any]]:
    """{name: {sha256, size_bytes, source_url}} from the committed
    manifest - never guessed, never generated at request time. Missing or
    unreadable manifest degrades to {} (no entries), not an exception."""
    if not MANIFEST_PATH.exists():
        return {}
    try:
        data = json.loads(MANIFEST_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("manifest.json exists but could not be parsed - ignoring it")
        return {}
    return data.get("artifacts", {})


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(DOWNLOAD_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _get_http_client() -> httpx.Client:
    """Seam for tests to substitute a MockTransport - see
    tests/test_artifacts.py. follow_redirects left at httpx's default
    (False) deliberately: a redirect (e.g. a GitHub Release asset URL
    always 302s) must never be silently followed and treated as the
    artifact's own bytes - see _download_and_verify's status check."""
    return httpx.Client(timeout=60.0)


def _download_and_verify(name: str, entry: dict[str, Any], dest: Path) -> bool:
    """Downloads entry['source_url'] to a unique temp file in bounded
    chunks, checks the result's sha256 against the manifest, and only then
    atomically renames it to `dest`. Returns False - with the temp file
    always removed, on every failure path, not just the empty-download
    case review found left partial files behind - if anything goes wrong.

    Each call uses its own temp file (tempfile.mkstemp, not a fixed
    `<name>.part` path) so two concurrent downloads of the same artifact
    (a second server process, or a race that slips past _lock_for) can
    never interleave writes into one shared file - each either finishes
    its own clean, independently-checksummed file and renames it into
    place, or fails and removes only its own temp file."""
    url = entry.get("source_url")
    expected_sha256 = entry.get("sha256")
    if not url or not expected_sha256:
        return False

    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".part")
    tmp_path = Path(tmp_name)
    try:
        written = 0
        try:
            # os.fdopen takes ownership of `fd` and closes it when this
            # `with` exits on ANY path below (including an early `return`
            # on a bad status code) - mkstemp's fd must never leak.
            with os.fdopen(fd, "wb") as fh, _get_http_client() as client, client.stream("GET", url) as response:
                # 2xx only - a redirect (3xx) must not have its (often
                # empty, or wrong-content) body written out and mistaken
                # for the artifact, or for a "checksum mismatch" when it's
                # really a misconfigured source_url. follow_redirects is
                # False, so a 3xx body carries no useful bytes anyway.
                if not (200 <= response.status_code < 300):
                    logger.warning(
                        "Artifact %s fetch failed: source returned %s", name, response.status_code
                    )
                    return False
                for chunk in response.iter_bytes(DOWNLOAD_CHUNK_BYTES):
                    written += len(chunk)
                    if written > MAX_ARTIFACT_BYTES:
                        logger.warning("Artifact %s exceeds the download size cap", name)
                        return False
                    fh.write(chunk)
        except (httpx.HTTPError, OSError) as exc:
            # OSError covers a write failure (e.g. ENOSPC on a small /tmp)
            # as well as a network-transport failure - both must fail
            # closed the same way, not propagate into _load_joblib as an
            # unhandled 500.
            logger.warning("Artifact %s fetch was interrupted: %s", name, exc)
            return False

        if written == 0:
            return False

        actual_sha256 = _sha256_of(tmp_path)
        if actual_sha256 != expected_sha256:
            logger.warning(
                "Artifact %s checksum mismatch (expected %s, got %s) - refusing to use it",
                name, expected_sha256, actual_sha256,
            )
            return False

        os.replace(tmp_path, dest)
        return True
    finally:
        # Unconditional - review found the previous "only if empty" guard
        # left a full-sized partial file on disk for every oversized or
        # interrupted download (a real risk on a small deployment /tmp).
        # A no-op once os.replace has already moved tmp_path to dest.
        tmp_path.unlink(missing_ok=True)


def _verified(path: Path, expected_sha256: str) -> bool:
    return path.exists() and _sha256_of(path) == expected_sha256


# (path, size, mtime_ns) -> sha256, so a multi-hundred-MB local artifact is
# hashed once per process rather than on every lookup.
_local_digests: dict[tuple[str, int, int], str] = {}


def _local_matches_manifest(path: Path) -> bool:
    """A local artifact that the manifest beside it records under a different
    sha256 is a stale or wrong model, not the validated one - refuse it
    rather than serve predictions from it. No manifest beside it, or no
    recorded sha256, keeps the local-development behaviour (used as-is)."""
    manifest_path = path.parent / MANIFEST_PATH.name
    if not manifest_path.exists():
        return True
    try:
        entry = json.loads(manifest_path.read_text()).get("artifacts", {}).get(path.name)
    except (json.JSONDecodeError, OSError, AttributeError):
        logger.warning("manifest.json beside %s could not be parsed - refusing it", path.name)
        return False
    if not isinstance(entry, dict) or not entry.get("sha256"):
        return True
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _local_digests:
        _local_digests[key] = _sha256_of(path)
    if _local_digests[key] != entry["sha256"]:
        logger.warning("Local artifact %s does not match its manifest sha256 - refusing it",
                       path.name)
        return False
    return True


def _is_safe_artifact_name(name: str) -> bool:
    """Defense in depth (security.md: validate any caller-supplied path, no
    traversal) - no current caller passes a non-literal name, but a bare
    filename check costs nothing and keeps that true if one ever does."""
    return Path(name).name == name and name not in ("", ".", "..")


def ensure_artifact(name: str) -> Path | None:
    """The path to read `name` from, or None if it cannot be obtained -
    never a guess, never a silently-wrong file. Checks, in order:
    1. Already present in the repo's own artifacts/models/ (local dev, or
       a deployment that mounted them some other way) - used as-is unless
       the manifest beside it records a different sha256, in which case it
       is refused (None), never silently served.
    2. Already fetched and checksum-verified earlier this process's
       lifetime (cached under _cache_dir()) - re-verified every call, not
       just trusted because a file exists at that path.
    3. Fetchable from the manifest's source_url - downloaded, verified
       against the manifest's sha256, and cached for next time.
    Any failure (unsafe name, no manifest entry, no source_url, no
    recorded sha256, checksum mismatch, network/disk failure) returns
    None - the caller's existing missing-artifact contract (_load_joblib
    returning None -> 503, never a crash or a silently wrong model).

    Review finding: a cached file is NEVER returned without a sha256 to
    check it against - a missing/corrupt manifest previously fell back to
    trusting any file already sitting in the cache directory, which (in a
    shared /tmp) another process could have planted there."""
    if not _is_safe_artifact_name(name):
        logger.warning("Refusing an unsafe artifact name: %r", name)
        return None

    local_path = MODELS_DIR / name
    if local_path.exists():
        return local_path if _local_matches_manifest(local_path) else None

    manifest = load_manifest()
    entry = manifest.get(name)
    if entry is None or not entry.get("sha256"):
        return None
    expected_sha256 = entry["sha256"]

    cached_path = _cache_dir() / name
    with _lock_for(name):
        if cached_path.exists() and _verified(cached_path, expected_sha256):
            return cached_path
        if cached_path.exists():
            # Stale/corrupted - never trust it just because a file exists.
            logger.warning("Cached artifact %s no longer matches the manifest - refetching", name)
            cached_path.unlink(missing_ok=True)

        if _download_and_verify(name, entry, cached_path):
            return cached_path
        return None
