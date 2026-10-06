"""Dataset archive manifest and secure ZIP handling (nightshift Phase D/E).

Scope: identify what a user-supplied archive/directory contains (without
guessing missing evidence) and extract ZIP archives defensively. Both
VERCEL_BOUNDED_MODE and LOCAL_FULL_MODE share the same safety checks; only
the numeric limits differ.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Dataset roles this project actually has adapters/evidence for.
DATASET_TYPES = (
    "femto_acquisition",
    "femto_bearing",
    "femto_learning_set",
    "femto_test_set",
    "femto_full_test_set",
    "college_run",
    "ims",
    "xjtu_sy",
    "generic_vibration",
    "analysis_bundle",
)

COMPATIBILITY_OUTCOMES = (
    "SUPPORTED_CLOUD",
    "SUPPORTED_OFFLINE",
    "ANALYSIS_BUNDLE_REQUIRED",
    "ADAPTER_REQUIRED",
    "INVALID_ARCHIVE",
)


@dataclass(frozen=True)
class DatasetArchiveManifest:
    """What we can prove about an uploaded archive/directory, nothing more."""

    dataset_type: str | None  # None == UNKNOWN, never guessed
    source_name: str
    sha256: str | None
    file_count: int
    compressed_size: int | None
    uncompressed_size: int
    bearing_run_ids: tuple[str, ...]
    acceleration_file_count: int
    temperature_file_count: int
    detected_schema: str | None
    compatibility: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ZipSecurityError(ValueError):
    """Raised when a ZIP fails a safety check. Never caught-and-ignored silently."""


# ponytail: fixed limits, not configurable per-request. Add a parameter if a
# caller legitimately needs a different bound.
@dataclass(frozen=True)
class ZipLimits:
    max_files: int
    max_uncompressed_bytes: int
    max_compression_ratio: float  # uncompressed/compressed per member


VERCEL_BOUNDED_MODE = ZipLimits(
    max_files=2_000, max_uncompressed_bytes=200 * 1024 * 1024, max_compression_ratio=100.0
)
LOCAL_FULL_MODE = ZipLimits(
    max_files=200_000, max_uncompressed_bytes=20 * 1024 * 1024 * 1024, max_compression_ratio=100.0
)


def _is_safe_member_path(name: str) -> bool:
    if name.startswith("/") or name.startswith("\\"):
        return False
    if ":" in name[:3]:  # Windows drive letter, e.g. "C:/..."
        return False
    parts = Path(name).parts
    return ".." not in parts


def safe_extract_zip(zip_path: str | Path, dest_dir: str | Path, limits: ZipLimits) -> list[str]:
    """Validate and extract a ZIP archive, rejecting anything unsafe.

    Returns the list of extracted member names. Raises ZipSecurityError on
    any violation -- callers must not blindly extractall() user input.
    """
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ZipSecurityError(f"malformed ZIP: {exc}") from exc

    with zf:
        infos = zf.infolist()
        if not infos:
            raise ZipSecurityError("empty ZIP archive")
        if len(infos) > limits.max_files:
            raise ZipSecurityError(f"archive has {len(infos)} entries, limit is {limits.max_files}")

        seen_normalized: set[str] = set()
        total_uncompressed = 0
        for info in infos:
            if info.flag_bits & 0x1:
                raise ZipSecurityError(f"encrypted entry not allowed: {info.filename}")
            if info.is_dir():
                continue
            if not _is_safe_member_path(info.filename):
                raise ZipSecurityError(f"unsafe path (traversal/absolute): {info.filename}")

            normalized = str(Path(info.filename).as_posix()).lower()
            if normalized in seen_normalized:
                raise ZipSecurityError(f"duplicate conflicting path: {info.filename}")
            seen_normalized.add(normalized)

            # zip-slip via symlink: a stored symlink's target is arbitrary and
            # is never followed by our own extraction, but reject the entry
            # outright so nothing downstream ever reads it as a symlink.
            unix_mode = info.external_attr >> 16
            is_symlink = bool(unix_mode) and (unix_mode & 0o170000) == 0o120000
            if is_symlink:
                raise ZipSecurityError(f"symlink entries are not allowed: {info.filename}")

            total_uncompressed += info.file_size
            if total_uncompressed > limits.max_uncompressed_bytes:
                raise ZipSecurityError(
                    f"uncompressed size exceeds {limits.max_uncompressed_bytes} bytes (zip-bomb guard)"
                )
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > limits.max_compression_ratio:
                    raise ZipSecurityError(
                        f"compression ratio {ratio:.0f}x exceeds limit for {info.filename} (zip-bomb guard)"
                    )

            # Reject nested archives outright -- this module does not recurse.
            if normalized.endswith((".zip", ".7z", ".tar", ".tar.gz", ".tgz")):
                raise ZipSecurityError(f"nested archive not allowed: {info.filename}")

        extracted: list[str] = []
        for info in infos:
            if info.is_dir():
                continue
            target = (dest / info.filename).resolve()
            if dest not in target.parents and target != dest:
                raise ZipSecurityError(f"resolved path escapes destination: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            extracted.append(info.filename)

    return extracted


def build_manifest_from_zip(zip_path: str | Path, sha256: str | None = None) -> DatasetArchiveManifest:
    """Inspect a ZIP's member names WITHOUT extracting, to classify it.

    Listing is safe; this never calls extractall(). Dataset type/role is left
    as None (UNKNOWN) whenever filenames don't give clear evidence -- see
    ml-data.md: "do not guess."
    """
    path = Path(zip_path)
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return DatasetArchiveManifest(
            dataset_type=None,
            source_name=path.name,
            sha256=sha256,
            file_count=0,
            compressed_size=None,
            uncompressed_size=0,
            bearing_run_ids=(),
            acceleration_file_count=0,
            temperature_file_count=0,
            detected_schema=None,
            compatibility="INVALID_ARCHIVE",
            warnings=("not a valid ZIP file",),
        )

    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        names = [i.filename for i in infos]
        acc_count = sum(1 for n in names if Path(n).name.startswith("acc_"))
        temp_count = sum(1 for n in names if Path(n).name.startswith("temp_"))
        college_count = sum(1 for n in names if Path(n).name.startswith("LogFile_"))
        bearing_ids = tuple(
            sorted({p.parts[-2] for n in names if (p := Path(n)).parts and len(p.parts) >= 2})
        )

        warnings: list[str] = []
        dataset_type: str | None = None
        compatibility = "ADAPTER_REQUIRED"

        if acc_count and any(b.lower().startswith("bearing") for b in bearing_ids):
            dataset_type = "femto_bearing"
            compatibility = "SUPPORTED_OFFLINE"
        elif college_count:
            dataset_type = "college_run"
            compatibility = "SUPPORTED_OFFLINE"
            if college_count < 129:
                warnings.append(f"only {college_count}/129 expected college files present")
        elif acc_count or temp_count:
            dataset_type = "femto_acquisition"
            compatibility = "SUPPORTED_OFFLINE"
        else:
            warnings.append("no recognized FEMTO/college filename pattern found")

        total_uncompressed = sum(i.file_size for i in infos)
        total_compressed = sum(i.compress_size for i in infos)
        if total_uncompressed > VERCEL_BOUNDED_MODE.max_uncompressed_bytes:
            compatibility = "ANALYSIS_BUNDLE_REQUIRED"
            warnings.append("uncompressed size exceeds Vercel bounded-mode limit")

        return DatasetArchiveManifest(
            dataset_type=dataset_type,
            source_name=path.name,
            sha256=sha256,
            file_count=len(infos),
            compressed_size=total_compressed,
            uncompressed_size=total_uncompressed,
            bearing_run_ids=bearing_ids,
            acceleration_file_count=acc_count,
            temperature_file_count=temp_count,
            detected_schema="femto_csv" if (acc_count or temp_count) else ("college_csv" if college_count else None),
            compatibility=compatibility,
            warnings=tuple(warnings),
        )


def demo() -> None:
    """ponytail self-check: exercise the safety gates without a real dataset."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # 1. legitimate small archive extracts fine
        good_zip = tmp_path / "good.zip"
        with zipfile.ZipFile(good_zip, "w") as zf:
            zf.writestr("Bearing2_1/acc_00001.csv", "1,2,3\n" * 10)
        extracted = safe_extract_zip(good_zip, tmp_path / "out", LOCAL_FULL_MODE)
        assert extracted == ["Bearing2_1/acc_00001.csv"]

        manifest = build_manifest_from_zip(good_zip)
        assert manifest.dataset_type == "femto_bearing"
        assert manifest.compatibility == "SUPPORTED_OFFLINE"
        assert manifest.bearing_run_ids == ("Bearing2_1",)

        # 2. path traversal rejected
        traversal_zip = tmp_path / "traversal.zip"
        with zipfile.ZipFile(traversal_zip, "w") as zf:
            zf.writestr("../../etc/passwd", "pwned")
        try:
            safe_extract_zip(traversal_zip, tmp_path / "out2", LOCAL_FULL_MODE)
            raise AssertionError("expected ZipSecurityError")
        except ZipSecurityError:
            pass

        # 3. zip-bomb (extreme ratio) rejected
        bomb_zip = tmp_path / "bomb.zip"
        with zipfile.ZipFile(bomb_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("x.csv", "0" * 50_000_000)
        try:
            safe_extract_zip(
                bomb_zip,
                tmp_path / "out3",
                ZipLimits(max_files=10, max_uncompressed_bytes=10_000_000, max_compression_ratio=50.0),
            )
            raise AssertionError("expected ZipSecurityError")
        except ZipSecurityError:
            pass

        # 4. nested archive rejected
        nested_zip = tmp_path / "nested.zip"
        with zipfile.ZipFile(nested_zip, "w") as zf:
            zf.writestr("inner.zip", "fake")
        try:
            safe_extract_zip(nested_zip, tmp_path / "out4", LOCAL_FULL_MODE)
            raise AssertionError("expected ZipSecurityError")
        except ZipSecurityError:
            pass

    print("archive.py demo: all checks passed")


if __name__ == "__main__":
    demo()
