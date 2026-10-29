"""RAR / multipart-RAR secure extraction (offline-only; see archive.py for ZIP).

RAR support is Offline Research Mode only -- never wired into the Vercel/API
path. Uses the system `7z` binary (already present; 7-Zip reads RAR/RAR5
natively) instead of adding a new Python dependency, per project rule:
`requirements.txt` is deliberately short.

Mirrors archive.py's security model: list before extract, reject path
traversal/absolute paths/symlinks/encrypted entries, enforce a file-count and
total-uncompressed-size limit, and a per-entry compression-ratio (zip-bomb
equivalent) guard. Extraction always targets a caller-supplied destination
directory, never the source directory.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from bearing_pdm.archive import LOCAL_FULL_MODE, ZipLimits

_PART_RE = re.compile(r"^(?P<stem>.+)\.part(?P<num>\d+)\.rar$", re.IGNORECASE)
_7Z_TIMEOUT_S = 1800
_MISSING_VOLUME_RE = re.compile(r"Missing volume\s*:\s*(\S+)")
_UNRAR_VOLUME_RE = re.compile(r"Details:.*\bvolume (\d+)")


class RarArchiveError(ValueError):
    """Raised for a missing/incomplete multipart set or a malformed RAR."""


class RarSecurityError(ValueError):
    """Raised when a RAR archive fails a safety check (mirrors ZipSecurityError)."""


@dataclass(frozen=True)
class RarEntry:
    path: str
    size: int
    packed_size: int
    is_symlink: bool
    encrypted: bool


def _require_7z() -> str:
    exe = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
    if exe is None:
        raise RarArchiveError("no `7z` binary found on this machine -- cannot read RAR archives")
    return exe


def _require_unrar() -> str:
    # 7z's bundled RAR decoder rejects some RAR5 compression methods real-world
    # archives use (verified against the project's actual XJTU-SY download:
    # "ERROR: Unsupported Method"); `unrar` extracts the same archive cleanly.
    # 7z remains the lister (list_rar_entries) since -slt gives clean, safety
    # checkable fields; unrar is extraction-only.
    exe = shutil.which("unrar")
    if exe is None:
        raise RarArchiveError("no `unrar` binary found on this machine -- cannot extract RAR archives")
    return exe


def discover_rar_parts(any_part_path: str | Path) -> list[Path]:
    """Given any `*.partNN.rar` of a set, return all parts in order (1..N).

    Raises RarArchiveError if the filename doesn't match the multipart
    pattern, or if any part in the contiguous 1..max sequence is missing.
    A single non-multipart `.rar` is also accepted and returned as-is.
    """
    path = Path(any_part_path)
    m = _PART_RE.match(path.name)
    if not m:
        if path.suffix.lower() == ".rar":
            if not path.is_file():
                raise RarArchiveError(f"not found: {path}")
            return [path]
        raise RarArchiveError(f"not a .rar file: {path}")

    stem = m.group("stem")
    directory = path.parent
    found: dict[int, Path] = {}
    for candidate in directory.glob(f"{stem}.part*.rar"):
        cm = _PART_RE.match(candidate.name)
        if cm and cm.group("stem") == stem:
            found[int(cm.group("num"))] = candidate

    if not found:
        raise RarArchiveError(f"no multipart RAR parts found for {stem!r} in {directory}")

    highest = max(found)
    missing = [n for n in range(1, highest + 1) if n not in found]
    if missing:
        raise RarArchiveError(
            f"incomplete multipart RAR set for {stem!r}: missing part(s) "
            f"{', '.join(f'{n:02d}' for n in missing)} (have {len(found)}/{highest})"
        )
    return [found[n] for n in range(1, highest + 1)]


def _is_safe_rar_member_path(name: str) -> bool:
    norm = name.replace("\\", "/")
    if norm.startswith("/"):
        return False
    if ":" in norm[:3]:  # Windows drive letter
        return False
    return ".." not in Path(norm).parts


def list_rar_entries(part01_path: str | Path) -> list[RarEntry]:
    """List (not extract) a RAR/multipart-RAR set's members via `7z l -slt`."""
    exe = _require_7z()
    try:
        result = subprocess.run(
            [exe, "l", "-slt", "--", str(part01_path)],
            capture_output=True,
            text=True,
            timeout=_7Z_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RarArchiveError(f"7z list timed out on {part01_path}") from exc
    if result.returncode != 0:
        missing = _MISSING_VOLUME_RE.findall(result.stdout + result.stderr)
        if missing:
            raise RarArchiveError(f"missing archive part: {', '.join(sorted(set(missing)))}")
        raise RarArchiveError(f"7z could not read {Path(part01_path).name}: "
                              f"{(result.stderr or result.stdout).strip()[-500:]}")

    entries: list[RarEntry] = []
    block: dict[str, str] = {}
    in_entries = False  # the "----------" line separates archive-header metadata from file entries

    def _flush() -> None:
        if in_entries and "Path" in block and block.get("Folder") != "+":
            entries.append(
                RarEntry(
                    path=block["Path"],
                    size=int(block.get("Size") or 0),
                    packed_size=int(block.get("Packed Size") or 0),
                    is_symlink=bool(block.get("Symbolic Link", "").strip()),
                    encrypted=block.get("Encrypted", "-").strip() == "+",
                )
            )
        block.clear()

    for line in result.stdout.splitlines():
        if line.strip().startswith("----"):
            _flush()
            in_entries = True
            continue
        if line.strip() == "":
            _flush()
            continue
        if " = " not in line:
            continue
        key, _, value = line.partition(" = ")
        block[key.strip()] = value.strip()
    _flush()

    if not entries:
        raise RarArchiveError(f"{part01_path}: archive has no file entries (empty or header-only)")
    return entries


def check_entries(entries: list[RarEntry], limits: ZipLimits = LOCAL_FULL_MODE) -> int:
    """Safety-check a listing before anything is extracted; returns total uncompressed bytes."""
    if len(entries) > limits.max_files:
        raise RarSecurityError(f"archive has {len(entries)} entries, limit is {limits.max_files}")
    total_uncompressed = 0
    for entry in entries:
        if entry.encrypted:
            raise RarSecurityError(f"encrypted entry not allowed: {entry.path}")
        if entry.is_symlink:
            raise RarSecurityError(f"symlink entries are not allowed: {entry.path}")
        if not _is_safe_rar_member_path(entry.path):
            raise RarSecurityError(f"unsafe path (traversal/absolute): {entry.path}")
        total_uncompressed += entry.size
        if total_uncompressed > limits.max_uncompressed_bytes:
            raise RarSecurityError(
                f"uncompressed size exceeds {limits.max_uncompressed_bytes} bytes (archive-bomb guard)"
            )
        if entry.packed_size > 0:
            ratio = entry.size / entry.packed_size
            if ratio > limits.max_compression_ratio:
                raise RarSecurityError(
                    f"compression ratio {ratio:.0f}x exceeds limit for {entry.path} (archive-bomb guard)"
                )
    return total_uncompressed


def rar_volume_number(path: str | Path) -> int | None:
    """1-based volume number read from the RAR header (not the filename), or
    None for a single-volume archive. Raises RarArchiveError if unreadable."""
    exe = _require_unrar()
    try:
        result = subprocess.run([exe, "l", "-p-", "--", str(path)], capture_output=True,
                                text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RarArchiveError(f"timed out reading {Path(path).name}") from exc
    m = _UNRAR_VOLUME_RE.search(result.stdout)
    if m:
        return int(m.group(1))
    if "Details:" in result.stdout:
        return None
    raise RarArchiveError(f"{Path(path).name} is not a readable RAR archive")


def list_rar_volume(path: str | Path) -> list[tuple[RarEntry, bool, bool]]:
    """Members stored in ONE RAR volume (`unrar lt` without -v lists only that
    volume), each with (continued_from_previous, continues_in_next). A non-solid
    RAR5 volume is readable on its own, so this works without the other parts."""
    exe = _require_unrar()
    try:
        result = subprocess.run([exe, "lt", "-p-", "--", str(path)], capture_output=True,
                                text=True, timeout=600, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RarArchiveError(f"timed out listing {Path(path).name}") from exc
    if "Details:" not in result.stdout:
        raise RarArchiveError(f"{Path(path).name} is not a readable RAR archive")
    if "solid" in result.stdout.split("Details:", 1)[1].splitlines()[0].lower():
        raise RarArchiveError(f"{Path(path).name} is a solid archive: its parts cannot be read "
                              "without all the parts before them")
    out: list[tuple[RarEntry, bool, bool]] = []
    for block in result.stdout.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            key, sep, value = line.partition(": ")
            if sep:
                fields[key.strip()] = value.strip()
        if "Name" not in fields or fields.get("Type", "File") == "Directory":
            continue
        ratio = fields.get("Ratio", "")
        out.append((RarEntry(path=fields["Name"], size=int(fields.get("Size") or 0),
                             packed_size=int(fields.get("Packed size") or 0),
                             is_symlink=fields.get("Type", "File") != "File",
                             encrypted="encrypt" in block.lower()),
                    ratio in ("<--", "<->"), ratio in ("-->", "<->")))
    return out


def extract_command(first_part: str | Path, dest: str | Path) -> list[str]:
    """Extractor argv for a checked archive: unrar for RAR (see _require_unrar), 7z otherwise."""
    if Path(first_part).suffix.lower() == ".rar":
        return [_require_unrar(), "x", "-y", "-o+", "-p-", "--", str(first_part), f"{dest}/"]
    return [_require_7z(), "x", "-y", f"-o{dest}", "--", str(first_part)]


def safe_extract_rar(
    any_part_path: str | Path, dest_dir: str | Path, limits: ZipLimits = LOCAL_FULL_MODE
) -> list[str]:
    """Validate a (multipart) RAR set and extract it into `dest_dir`.

    Requires the complete part sequence starting at part01 (discover_rar_parts
    raises on a gap). Extraction always starts from part01; 7z follows the
    volume chain itself using the other parts found alongside it.
    """
    parts = discover_rar_parts(any_part_path)
    part01 = parts[0]

    entries = list_rar_entries(part01)
    total_uncompressed = check_entries(entries, limits)

    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(dest).free
    if total_uncompressed > free_bytes:
        raise RarArchiveError(
            f"not enough free space at {dest}: need {total_uncompressed} bytes, "
            f"{free_bytes} available"
        )
    exe = _require_unrar()
    try:
        result = subprocess.run(
            [exe, "x", "-y", "-o+", "--", str(part01), f"{dest}/"],
            capture_output=True,
            text=True,
            timeout=_7Z_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RarArchiveError(f"unrar extraction timed out on {part01}") from exc
    # unrar exit code 1 is "non-fatal warning" (e.g. trailing bytes after a
    # multivolume's logical end, seen on real downloads) -- not a failure.
    # >=2 and the literal "aborted"/"ERROR:" markers are real failures.
    if result.returncode not in (0, 1) or "Program aborted" in result.stdout:
        raise RarArchiveError(f"unrar extraction failed for {part01}: {result.stdout.strip()[:500]}")

    # Defense in depth: confirm nothing landed outside dest (7z already resolved
    # paths internally, but we never trust an external tool's output unchecked).
    extracted: list[str] = []
    for entry in entries:
        target = (dest / entry.path.replace("\\", "/")).resolve()
        if dest not in target.parents and target != dest:
            raise RarSecurityError(f"resolved path escapes destination: {entry.path}")
        extracted.append(entry.path)
    return extracted


def demo() -> None:
    """ponytail self-check: exercise part-discovery gap detection without a real RAR."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for n in (1, 2, 4):  # gap at part03
            (tmp_path / f"set.part{n:02d}.rar").write_bytes(b"not a real rar")
        try:
            discover_rar_parts(tmp_path / "set.part01.rar")
            raise AssertionError("expected RarArchiveError for missing part03")
        except RarArchiveError as exc:
            assert "part03" in str(exc) or "03" in str(exc)

        for n in (1, 2, 3):
            (tmp_path / f"complete.part{n:02d}.rar").write_bytes(b"x")
        parts = discover_rar_parts(tmp_path / "complete.part02.rar")
        assert [p.name for p in parts] == [
            "complete.part01.rar",
            "complete.part02.rar",
            "complete.part03.rar",
        ]

        assert _is_safe_rar_member_path("Bearing1_1/1.csv")
        assert not _is_safe_rar_member_path("../../etc/passwd")
        assert not _is_safe_rar_member_path("/etc/passwd")
        assert not _is_safe_rar_member_path("C:/Windows/system32")

    print("rar_archive.py demo: all checks passed")


if __name__ == "__main__":
    demo()
