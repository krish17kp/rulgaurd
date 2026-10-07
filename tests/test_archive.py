from __future__ import annotations

import zipfile

import pytest

from bearing_pdm.archive import (
    LOCAL_FULL_MODE,
    VERCEL_BOUNDED_MODE,
    ZipLimits,
    ZipSecurityError,
    build_manifest_from_zip,
    safe_extract_zip,
)


def _make_zip(path, entries: dict[str, bytes | str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_valid_femto_bearing_zip_extracts(tmp_path):
    zip_path = tmp_path / "bearing.zip"
    _make_zip(
        zip_path,
        {
            "Bearing2_1/acc_00001.csv": "1,2,3\n",
            "Bearing2_1/temp_00001.csv": "4,5\n",
        },
    )
    extracted = safe_extract_zip(zip_path, tmp_path / "out", LOCAL_FULL_MODE)
    assert set(extracted) == {"Bearing2_1/acc_00001.csv", "Bearing2_1/temp_00001.csv"}
    assert (tmp_path / "out" / "Bearing2_1" / "acc_00001.csv").read_text() == "1,2,3\n"


def test_manifest_detects_femto_bearing(tmp_path):
    zip_path = tmp_path / "bearing.zip"
    _make_zip(zip_path, {f"Bearing2_1/acc_{i:05d}.csv": "x\n" for i in range(5)})
    manifest = build_manifest_from_zip(zip_path)
    assert manifest.dataset_type == "femto_bearing"
    assert manifest.compatibility == "SUPPORTED_OFFLINE"
    assert manifest.bearing_run_ids == ("Bearing2_1",)
    assert manifest.acceleration_file_count == 5


def test_manifest_detects_college(tmp_path):
    zip_path = tmp_path / "college.zip"
    _make_zip(zip_path, {"LogFile_2022-01-01.csv": "x\n"})
    manifest = build_manifest_from_zip(zip_path)
    assert manifest.dataset_type == "college_run"
    assert "only 1/129" in manifest.warnings[0]


def test_manifest_unknown_when_no_evidence(tmp_path):
    zip_path = tmp_path / "mystery.zip"
    _make_zip(zip_path, {"readme.txt": "hello"})
    manifest = build_manifest_from_zip(zip_path)
    assert manifest.dataset_type is None
    assert manifest.compatibility == "ADAPTER_REQUIRED"


def test_malformed_zip_reports_invalid(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    manifest = build_manifest_from_zip(bad)
    assert manifest.compatibility == "INVALID_ARCHIVE"
    with pytest.raises(ZipSecurityError):
        safe_extract_zip(bad, tmp_path / "out", LOCAL_FULL_MODE)


def test_path_traversal_rejected(tmp_path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"../../etc/passwd": "pwned"})
    with pytest.raises(ZipSecurityError, match="unsafe path"):
        safe_extract_zip(zip_path, tmp_path / "out", LOCAL_FULL_MODE)


def test_absolute_path_rejected(tmp_path):
    zip_path = tmp_path / "evil2.zip"
    _make_zip(zip_path, {"/etc/passwd": "pwned"})
    with pytest.raises(ZipSecurityError, match="unsafe path"):
        safe_extract_zip(zip_path, tmp_path / "out", LOCAL_FULL_MODE)


def test_zip_bomb_ratio_rejected(tmp_path):
    zip_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("x.csv", "0" * 50_000_000)
    with pytest.raises(ZipSecurityError, match="compression ratio|uncompressed size"):
        safe_extract_zip(
            zip_path,
            tmp_path / "out",
            ZipLimits(max_files=10, max_uncompressed_bytes=10_000_000, max_compression_ratio=50.0),
        )


def test_excessive_file_count_rejected(tmp_path):
    zip_path = tmp_path / "many.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for i in range(5):
            zf.writestr(f"f{i}.csv", "x")
    with pytest.raises(ZipSecurityError, match="limit"):
        safe_extract_zip(zip_path, tmp_path / "out", ZipLimits(max_files=3, max_uncompressed_bytes=10**9, max_compression_ratio=100))


def test_nested_archive_rejected(tmp_path):
    zip_path = tmp_path / "nested.zip"
    _make_zip(zip_path, {"inner.zip": "fake"})
    with pytest.raises(ZipSecurityError, match="nested archive"):
        safe_extract_zip(zip_path, tmp_path / "out", LOCAL_FULL_MODE)


def test_duplicate_path_rejected(tmp_path):
    zip_path = tmp_path / "dupe.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.csv", "1")
        zf.writestr("A.csv", "2")
    with pytest.raises(ZipSecurityError, match="duplicate"):
        safe_extract_zip(zip_path, tmp_path / "out", LOCAL_FULL_MODE)


def test_empty_zip_rejected(tmp_path):
    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w"):
        pass
    with pytest.raises(ZipSecurityError, match="empty"):
        safe_extract_zip(zip_path, tmp_path / "out", LOCAL_FULL_MODE)


def test_encrypted_zip_rejected(tmp_path):
    # True AES/ZipCrypto encryption needs pyzipper (not a project dependency);
    # set the general-purpose encryption bit directly on the ZipInfo before
    # writing, which is what zipfile itself checks when reading flag_bits.
    zip_path = tmp_path / "enc.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("secret.csv", "data")
        zf.filelist[0].flag_bits |= 0x1  # mutate before the central directory is flushed on close
    with pytest.raises(ZipSecurityError, match="encrypted"):
        safe_extract_zip(zip_path, tmp_path / "out", LOCAL_FULL_MODE)


def test_symlink_entry_rejected(tmp_path):
    zip_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        info = zipfile.ZipInfo("link.csv")
        info.external_attr = (0o120777 << 16)  # S_IFLNK | rwxrwxrwx
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(ZipSecurityError, match="symlink"):
        safe_extract_zip(zip_path, tmp_path / "out", LOCAL_FULL_MODE)


def test_vercel_bounded_mode_flags_oversized_manifest(tmp_path):
    zip_path = tmp_path / "big.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("Bearing1_1/acc_00001.csv", "x" * (VERCEL_BOUNDED_MODE.max_uncompressed_bytes + 1))
    manifest = build_manifest_from_zip(zip_path)
    assert manifest.compatibility == "ANALYSIS_BUNDLE_REQUIRED"
