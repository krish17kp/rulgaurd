from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bearing_pdm.rar_archive import (
    RarArchiveError,
    _is_safe_rar_member_path,
    discover_rar_parts,
    list_rar_entries,
)

_REAL_XJTU_PART01 = Path.home() / "Downloads/XJTU_parts/Data/XJTU-SY_Bearing_Datasets.part01.rar"
_HAS_7Z = shutil.which("7z") is not None
_HAS_UNRAR = shutil.which("unrar") is not None


def test_discover_rar_parts_complete_sequence(tmp_path):
    for n in (1, 2, 3):
        (tmp_path / f"set.part{n:02d}.rar").write_bytes(b"x")
    parts = discover_rar_parts(tmp_path / "set.part02.rar")
    assert [p.name for p in parts] == [
        "set.part01.rar",
        "set.part02.rar",
        "set.part03.rar",
    ]


def test_discover_rar_parts_missing_part_raises(tmp_path):
    for n in (1, 2, 4):  # part03 missing
        (tmp_path / f"set.part{n:02d}.rar").write_bytes(b"x")
    with pytest.raises(RarArchiveError, match="part03|03"):
        discover_rar_parts(tmp_path / "set.part01.rar")


def test_discover_rar_parts_single_rar_accepted(tmp_path):
    single = tmp_path / "single.rar"
    single.write_bytes(b"x")
    assert discover_rar_parts(single) == [single]


def test_discover_rar_parts_missing_file_raises(tmp_path):
    with pytest.raises(RarArchiveError):
        discover_rar_parts(tmp_path / "nope.rar")


def test_discover_rar_parts_non_rar_rejected(tmp_path):
    bogus = tmp_path / "not_a_rar.txt"
    bogus.write_text("x")
    with pytest.raises(RarArchiveError):
        discover_rar_parts(bogus)


@pytest.mark.parametrize(
    "name,safe",
    [
        ("Bearing1_1/1.csv", True),
        ("35Hz12kN/Bearing1_1/1.csv", True),
        ("../../etc/passwd", False),
        ("/etc/passwd", False),
        ("C:/Windows/system32", False),
        (r"..\..\windows\win.ini", False),
    ],
)
def test_is_safe_rar_member_path(name, safe):
    assert _is_safe_rar_member_path(name) is safe


@pytest.mark.skipif(not _HAS_7Z, reason="7z binary not available on this machine")
def test_list_rar_entries_malformed_raises(tmp_path):
    bad = tmp_path / "bad.rar"
    bad.write_bytes(b"not a real rar file")
    with pytest.raises(RarArchiveError):
        list_rar_entries(bad)


@pytest.mark.skipif(
    not (_HAS_7Z and _HAS_UNRAR and _REAL_XJTU_PART01.exists()),
    reason="real XJTU-SY multipart RAR download not present on this machine",
)
def test_real_xjtu_multipart_rar_discovered_and_listed():
    """Integration check against the actual XJTU-SY download (not a committed
    fixture -- too large). Verifies part-set completeness and entry listing
    without doing the full multi-GB extraction on every test run (that path
    was verified manually: 9217 entries, 15 bearings, 2.csv/4.csv recognized
    as XJTU rather than FEMTO acquisitions)."""
    parts = discover_rar_parts(_REAL_XJTU_PART01)
    assert len(parts) == 6
    assert [p.name for p in parts] == [
        f"XJTU-SY_Bearing_Datasets.part{n:02d}.rar" for n in range(1, 7)
    ]

    entries = list_rar_entries(_REAL_XJTU_PART01)
    assert len(entries) > 9000
    names = {e.path for e in entries}
    assert "XJTU-SY_Bearing_Datasets/35Hz12kN/Bearing1_1/1.csv" in names
    assert "XJTU-SY_Bearing_Datasets/35Hz12kN/Bearing1_1/2.csv" in names
    assert not any(e.encrypted for e in entries)
    assert not any(e.is_symlink for e in entries)
