"""Whole-dataset upload jobs: archive set -> check -> extract -> detect -> process -> route.

One job = one archive set (a ZIP, a 7Z, a RAR, a multi-part `.partNN.rar` or
`.7z.NNN` set) or a folder of loose files. The browser uploads each file in
resumable chunks (`append_chunk`), then `start_job` hands the job to a detached
worker process (`python -m bearing_pdm.dataset_jobs run <id>`), so processing
survives the page being closed and an out-of-memory worker cannot take the API
down. Only one worker runs at a time (the VPS has one CPU); others wait queued.

State lives in `<JOBS_ROOT>/<id>/state.json` (atomic replace), so any API
process can report progress. Retention: raw uploads and extracted data are
deleted as soon as a job finishes, fails or is cancelled; incomplete uploads
idle for INCOMPLETE_TTL_S are deleted; results are kept for RESULT_TTL_S.

The scientific path is unchanged: dataset adapters -> build_canonical_features
-> routing.route_dataset (the same gate scripts/analyze_dataset.py uses). A
dataset no model has shown held-out skill on gets inspection results (health
indicator, stage, applicability) and RUL is withheld by that gate - never
manufactured here.

A format no adapter recognises pauses in `needs_mapping` with a proposed column
mapping (profiler names, else a labelled guess); nothing is processed until the
user confirms the vibration columns, sampling rate and recording interval
(`submit_mapping`). The worker then runs the same path through GenericAdapter.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import posixpath
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from bearing_pdm.archive import LOCAL_FULL_MODE, ZipSecurityError, safe_extract_zip
from bearing_pdm.rar_archive import (
    RarArchiveError,
    RarSecurityError,
    check_entries,
    extract_command,
    list_rar_entries,
    list_rar_volume,
    rar_volume_number,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
JOBS_ROOT = Path(os.environ.get("RULGUARD_JOBS_DIR", "/data/jobs"))

MAX_JOB_BYTES = 20 * 1024**3          # declared upload total per job
MAX_FILES_PER_JOB = 20_000            # folder upload
MAX_PARTS = 200
MAX_CHUNK_BYTES = 32 * 1024**2        # under the API body limit and nginx's 70m
MAX_OPEN_JOBS = 3                     # not-yet-finished jobs holding disk
DISK_MARGIN_BYTES = 2 * 1024**3
INCOMPLETE_TTL_S = 6 * 3600
RESULT_TTL_S = 7 * 24 * 3600
HEARTBEAT_STALE_S = 15 * 60
EXTRACT_TIMEOUT_S = 3 * 3600

ARCHIVE_SUFFIXES = (".zip", ".7z", ".rar")
TERMINAL = ("completed", "partial", "failed", "cancelled")
ACTIVE = ("queued", "checking", "extracting", "detecting", "processing")
GENERIC_ROLES = ("vibration_x", "vibration_y", "temperature_bearing", "temperature_ambient")
STAGES = ("upload", "check", "extract", "detect", "process")

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,32}$")
_RAR_PART_RE = re.compile(r"^(?P<stem>.+)\.part(?P<num>\d+)\.rar$", re.IGNORECASE)
_7Z_PART_RE = re.compile(r"^(?P<stem>.+\.7z)\.(?P<num>\d{3})$", re.IGNORECASE)
_UNSUPPORTED_SPLIT_RE = re.compile(r"\.(z\d{2}|r\d{2}|zip\.\d{3})$", re.IGNORECASE)
_KNOWN_PART_COUNTS = {"xjtu-sy_bearing_datasets": 6}  # official XJTU-SY download


class JobError(ValueError):
    """A request the user can fix (bad file set, missing part, wrong offset)."""

    def __init__(self, message: str, code: str = "INVALID_JOB", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


class _Cancelled(Exception):
    pass


# ---------------------------------------------------------------------------
# Planning: what did the user select?
# ---------------------------------------------------------------------------


def _safe_relpath(name: str) -> str:
    norm = name.replace("\\", "/").strip()
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts or norm.startswith("/") or ":" in norm[:3] or ".." in parts:
        raise JobError(f"unsafe file name: {name!r}")
    if len(norm) > 512 or any(len(p) > 255 for p in parts):
        raise JobError(f"file name too long: {name[:80]!r}")
    return "/".join(parts)


def _part_name(example: str, num: int, kind: str) -> str:
    if kind == "multipart_rar":
        m = _RAR_PART_RE.match(example)
        return f"{m.group('stem')}.part{num:0{len(m.group('num'))}d}.rar"
    m = _7Z_PART_RE.match(example)
    return f"{m.group('stem')}.{num:03d}"


def plan_upload(files: list[dict]) -> dict:
    """Classify a selection and refuse anything that cannot be a complete set.

    Returns {"kind", "files": [{"name", "size"}] in processing order,
    "first": the name extraction starts from (archives), "total_bytes", "notes"}.
    """
    if not files:
        raise JobError("no files selected")
    if len(files) > MAX_FILES_PER_JOB:
        raise JobError(f"{len(files):,} files selected; the limit is {MAX_FILES_PER_JOB:,} per job")
    entries = []
    for f in files:
        size = f.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise JobError(f"invalid size for {f.get('name')!r}")
        entries.append({"name": _safe_relpath(str(f.get("name", ""))), "size": size})
    total = sum(e["size"] for e in entries)
    if total > MAX_JOB_BYTES:
        raise JobError(f"selection is {total / 1024**3:.1f} GB; the limit is "
                       f"{MAX_JOB_BYTES / 1024**3:.0f} GB per job", code="TOO_LARGE", status=413)
    names = [e["name"] for e in entries]
    if len({n.lower() for n in names}) != len(names):
        raise JobError("the same file was selected twice")
    for n in names:
        if _UNSUPPORTED_SPLIT_RE.search(n):
            raise JobError(f"{Path(n).name}: split ZIP (.z01) and old-style RAR (.r00) volumes are "
                           "not supported. Extract the set on your computer and upload the folder, "
                           "or one ZIP.", code="UNSUPPORTED_FORMAT")

    def is_archive(n: str) -> bool:
        return n.lower().endswith(ARCHIVE_SUFFIXES) or bool(_7Z_PART_RE.match(Path(n).name))

    archives = [e for e in entries if is_archive(e["name"])]
    if not archives:
        return {"kind": "files", "files": sorted(entries, key=lambda e: e["name"]),
                "first": None, "total_bytes": total, "notes": []}
    if len(archives) != len(entries):
        raise JobError("archives and loose files were selected together. Upload one archive set, "
                       "or one folder of data files, per analysis.")
    for e in archives:
        e["name"] = Path(e["name"]).name
        if e["size"] == 0:
            raise JobError(f"{e['name']} is empty (0 bytes)")

    single = archives[0]["name"]
    if len(archives) == 1 and not (_RAR_PART_RE.match(single) or _7Z_PART_RE.match(single)):
        return {"kind": Path(single).suffix.lower().lstrip("."), "files": archives,
                "first": single, "total_bytes": total, "notes": []}

    parts: dict[int, dict] = {}
    stems, kinds = set(), set()
    for e in archives:
        m = _RAR_PART_RE.match(e["name"]) or _7Z_PART_RE.match(e["name"])
        if not m:
            raise JobError(f"{e['name']} is not part of a multi-part set, but several archives were "
                           "selected. Upload one archive (or one complete set of parts) at a time.")
        stems.add(m.group("stem").lower())
        kinds.add("multipart_rar" if m.re is _RAR_PART_RE else "multipart_7z")
        num = int(m.group("num"))
        if num in parts:
            raise JobError(f"part {num} was selected twice ({parts[num]['name']} and {e['name']})")
        parts[num] = e
    if len(stems) > 1 or len(kinds) > 1:
        raise JobError("the selected parts belong to different archives: " + ", ".join(sorted(stems)))
    if len(parts) > MAX_PARTS:
        raise JobError(f"{len(parts)} parts; the limit is {MAX_PARTS}")
    kind, stem_key = kinds.pop(), stems.pop()
    example = next(iter(parts.values()))["name"]
    known_total = _KNOWN_PART_COUNTS.get(stem_key.removesuffix(".7z"))
    last = max(max(parts), known_total or 0)
    missing = [_part_name(example, n, kind) for n in range(1, last + 1) if n not in parts]
    if missing and kind == "multipart_7z":
        # .7z.NNN is a plain byte split: no part is readable without all those before it.
        raise JobError(f"incomplete multi-part archive: missing {', '.join(missing)}. A split 7z "
                       "archive can only be extracted with every part, starting from .001.",
                       code="MISSING_PARTS")
    notes = [] if known_total else [
        "The total number of parts cannot be known from file names alone. After upload, the "
        "archive headers are read to confirm the last part is present."]
    if missing:
        of = f"{known_total}" if known_total else f"at least {last}"
        notes.insert(0, (
            f"Only {len(parts)} of {of} parts selected (missing: {', '.join(missing)}). Each RAR "
            "part can be read on its own, so the recordings stored completely inside the selected "
            "part(s) are analysed; the recordings in the missing parts are not. A recording split "
            "across a missing part is skipped, and a bearing cut by a missing part is reported as "
            "incomplete, with no end-of-life label. Select every part to analyse the whole dataset."))
    ordered = [parts[n] for n in sorted(parts)]
    return {"kind": kind, "files": ordered, "first": ordered[0]["name"], "total_bytes": total,
            "notes": notes, "missing": missing, "expected_parts": last}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def job_dir(job_id: str) -> Path:
    if not _ID_RE.match(job_id or ""):
        raise JobError("unknown job", code="NOT_FOUND", status=404)
    d = JOBS_ROOT / job_id
    if not (d / "state.json").is_file():
        raise JobError("unknown or expired job", code="NOT_FOUND", status=404)
    return d


def _read_state(d: Path) -> dict:
    return json.loads((d / "state.json").read_text())


def _json_clean(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_clean(v) for v in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if hasattr(value, "item"):  # numpy scalar
        return _json_clean(value.item())
    return str(value)


def _write_state(d: Path, state: dict) -> None:
    state["updated_at"] = time.time()
    tmp = d / f"state.json.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(_json_clean(state)))
    os.replace(tmp, d / "state.json")


def _update(d: Path, **changes: Any) -> dict:
    """Worker-side state change; raises _Cancelled once the user cancelled."""
    state = _read_state(d)
    if state["state"] == "cancelled":
        raise _Cancelled()
    for key, value in changes.items():
        if key == "stages":
            for stage, fields in value.items():
                state["stages"][stage].update(fields)
        else:
            state[key] = value
    _write_state(d, state)
    return state


def _stored_path(d: Path, plan: dict, index: int) -> Path:
    base = d / ("data" if plan["kind"] == "files" else "upload")
    return base / plan["files"][index]["name"]


def _received(d: Path, plan: dict) -> list[int]:
    out = []
    for i in range(len(plan["files"])):
        p = _stored_path(d, plan, i)
        out.append(p.stat().st_size if p.exists() else 0)
    return out


def _all_states() -> list[dict]:
    out = []
    if JOBS_ROOT.is_dir():
        for d in JOBS_ROOT.iterdir():
            try:
                out.append(_read_state(d))
            except (OSError, ValueError):
                continue
    return out


def _pending_bytes(state: dict) -> int:
    if state["state"] != "awaiting_upload":
        return 0
    return max(state["plan"]["total_bytes"]
               - sum(_received(JOBS_ROOT / state["id"], state["plan"])), 0)


def create_job(files: list[dict]) -> dict:
    plan = plan_upload(files)
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    sweep()
    open_jobs = [s for s in _all_states() if s["state"] not in TERMINAL]
    if len(open_jobs) >= MAX_OPEN_JOBS:
        raise JobError("the server is already handling the maximum number of dataset uploads. "
                       "Try again later.", code="BUSY", status=429)
    reserved = sum(_pending_bytes(s) for s in open_jobs)
    free = shutil.disk_usage(JOBS_ROOT).free
    if plan["total_bytes"] + reserved + DISK_MARGIN_BYTES > free:
        raise JobError(f"not enough server disk space for {plan['total_bytes'] / 1024**3:.1f} GB "
                       f"(about {max(free - reserved - DISK_MARGIN_BYTES, 0) / 1024**3:.1f} GB "
                       "is available for uploads now).", code="INSUFFICIENT_STORAGE", status=507)
    job_id = secrets.token_urlsafe(12)
    d = JOBS_ROOT / job_id
    (d / ("data" if plan["kind"] == "files" else "upload")).mkdir(parents=True)
    state = {
        "id": job_id, "created_at": time.time(), "state": "awaiting_upload", "plan": plan,
        "message": "Waiting for the files to be uploaded.", "error": None,
        "stages": {s: {"status": "pending", "done": 0, "total": 0, "detail": ""} for s in STAGES},
        "summary": None, "validation": None, "pid": None,
    }
    state["stages"]["upload"]["total"] = plan["total_bytes"]
    if plan["kind"] == "files":
        state["stages"]["check"].update(status="skipped", detail="Loose files: no archive to check.")
        state["stages"]["extract"].update(status="skipped", detail="Loose files: nothing to extract.")
    _write_state(d, state)
    return public_state(d, all_files=True)


def public_state(d: Path, all_files: bool = False) -> dict:
    state = _read_state(d)
    if state["state"] in ACTIVE and _worker_lost(state):
        state = _fail(d, "Processing was interrupted (the server restarted or the worker stopped). "
                         "Start a new upload to try again.")
    plan = state["plan"]
    received = (_received(d, plan) if state["state"] == "awaiting_upload"
                else [f["size"] if state["stages"]["upload"]["status"] == "done" else 0
                      for f in plan["files"]])
    if state["state"] == "awaiting_upload":
        state["stages"]["upload"].update(done=sum(received),
                                         status="running" if sum(received) else "pending")
    files = [{"name": f["name"], "size": f["size"], "received": r}
             for f, r in zip(plan["files"], received, strict=True)]
    state["file_count"] = len(files)
    # A folder upload can hold thousands of files: list only what still needs bytes.
    state["files"] = (files if all_files or len(files) <= 50
                      else [f for f in files if f["received"] < f["size"]][:50])
    state["plan"] = {k: plan.get(k, []) for k in ("kind", "first", "total_bytes", "notes",
                                                   "missing")}
    state.pop("pid", None)
    state["has_result"] = (d / "result.json").is_file()
    return _json_clean(state)


def _file_index(plan: dict, index: int) -> int:
    if not 0 <= index < len(plan["files"]):
        raise JobError("unknown file index", code="NOT_FOUND", status=404)
    return index


def file_offset(job_id: str, index: int) -> int:
    d = job_dir(job_id)
    plan = _read_state(d)["plan"]
    p = _stored_path(d, plan, _file_index(plan, index))
    return p.stat().st_size if p.exists() else 0


def append_chunk(job_id: str, index: int, offset: int, data: bytes) -> int:
    """Append one chunk at `offset`; returns the bytes now held for that file.

    Resumable: after an interruption the client reads the received count
    (public_state / file_offset) and continues from there. A wrong offset is
    rejected, never patched over."""
    d = job_dir(job_id)
    state = _read_state(d)
    if state["state"] != "awaiting_upload":
        raise JobError("this job is no longer accepting uploads", code="CONFLICT", status=409)
    plan = state["plan"]
    expected = plan["files"][_file_index(plan, index)]["size"]
    if len(data) > MAX_CHUNK_BYTES:
        raise JobError("chunk is larger than allowed", code="CHUNK_TOO_LARGE", status=413)
    path = _stored_path(d, plan, index)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        have = fh.seek(0, os.SEEK_END)
        if offset != have:
            raise JobError(f"offset {offset} does not match the {have} bytes already received",
                           code="OFFSET_MISMATCH", status=409)
        if have + len(data) > expected:
            raise JobError("chunk runs past the declared file size", code="CHUNK_TOO_LARGE",
                           status=413)
        fh.write(data)
        return have + len(data)


def start_job(job_id: str) -> dict:
    d = job_dir(job_id)
    state = _read_state(d)
    if state["state"] != "awaiting_upload":
        raise JobError(f"job is already {state['state']}", code="CONFLICT", status=409)
    plan = state["plan"]
    incomplete = [f["name"] for f, r in zip(plan["files"], _received(d, plan), strict=True)
                  if r != f["size"]]
    if incomplete:
        raise JobError(f"{len(incomplete)} file(s) are not fully uploaded yet: "
                       + ", ".join(incomplete[:5]), code="UPLOAD_INCOMPLETE", status=409)
    state["state"] = "queued"
    state["message"] = "Uploaded. Waiting for the processing worker."
    state["stages"]["upload"].update(status="done", done=plan["total_bytes"])
    _write_state(d, state)
    pid = _spawn_worker(d, job_id)
    if pid is not None:
        state = _read_state(d)
        state["pid"] = pid
        _write_state(d, state)
    return public_state(d)


def _spawn_worker(d: Path, job_id: str) -> int | None:
    with open(d / "worker.log", "ab") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "bearing_pdm.dataset_jobs", "run", job_id],
            cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True, env={**os.environ, "RULGUARD_JOBS_DIR": str(JOBS_ROOT)},
        )
    threading.Thread(target=proc.wait, daemon=True).start()  # reap: no zombie worker
    return proc.pid


def cancel_job(job_id: str) -> dict:
    d = job_dir(job_id)
    state = _read_state(d)
    if state["state"] not in TERMINAL:
        pid = state.get("pid")
        state.update(state="cancelled", message="Cancelled. Uploaded and extracted files were deleted.")
        _write_state(d, state)
        if pid and _pid_is_worker(pid, job_id):
            try:
                os.killpg(pid, 9)
            except ProcessLookupError:
                pass
        _delete_raw(d)
    return public_state(d)


def read_result(job_id: str) -> dict:
    path = job_dir(job_id) / "result.json"
    if not path.is_file():
        raise JobError("no result for this job (yet)", code="NOT_FOUND", status=404)
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------


def _delete_raw(d: Path) -> None:
    for sub in ("upload", "data"):
        shutil.rmtree(d / sub, ignore_errors=True)


def _pid_is_worker(pid: int, job_id: str) -> bool:
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return job_id.encode() in cmd and ") Z " not in stat


def _worker_lost(state: dict) -> bool:
    if time.time() - state.get("updated_at", 0) > HEARTBEAT_STALE_S:
        return True
    pid = state.get("pid")
    return pid is not None and not _pid_is_worker(pid, state["id"])


def _fail(d: Path, message: str) -> dict:
    state = _read_state(d)
    for stage in state["stages"].values():
        if stage["status"] in ("running", "pending"):
            stage["status"] = "failed" if stage["status"] == "running" else "skipped"
    state.update(state="failed", message=message, error=message)
    _write_state(d, state)
    _delete_raw(d)
    return state


def sweep() -> None:
    """Apply the retention policy (module docstring). Called on job creation."""
    now = time.time()
    for state in _all_states():
        d = JOBS_ROOT / state["id"]
        if state["state"] in TERMINAL:
            _delete_raw(d)
            if now - state.get("updated_at", 0) > RESULT_TTL_S:
                shutil.rmtree(d, ignore_errors=True)
        elif state["state"] == "needs_mapping":
            if now - state.get("updated_at", 0) > INCOMPLETE_TTL_S:
                shutil.rmtree(d, ignore_errors=True)
        elif state["state"] == "awaiting_upload":
            latest = max([state.get("updated_at", 0)]
                         + [p.stat().st_mtime for p in d.rglob("*") if p.is_file()])
            if now - latest > INCOMPLETE_TTL_S:
                shutil.rmtree(d, ignore_errors=True)
        elif _worker_lost(state):
            _fail(d, "Processing was interrupted (the server restarted or the worker stopped). "
                     "Start a new upload to try again.")


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def _dir_bytes(root: Path) -> tuple[int, int]:
    total = count = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
                count += 1
            except OSError:
                pass
    return total, count


def _safe_message(exc: BaseException | str, d: Path) -> str:
    """Error text for the UI: server paths stripped, length capped."""
    text = str(exc)
    for prefix in (f"{d / 'data'}/", f"{d / 'upload'}/", str(d), str(JOBS_ROOT), str(REPO_ROOT)):
        text = text.replace(prefix, "")
    return text[:400]


def _check_archive(d: Path, plan: dict) -> int:
    """Confirm the part set from the archive headers and safety-check the
    listing before anything is extracted. Returns total uncompressed bytes."""
    upload = d / "upload"
    first = upload / plan["first"]
    if plan["kind"] == "zip":
        import zipfile
        try:
            with zipfile.ZipFile(first) as zf:
                infos = [i for i in zf.infolist() if not i.is_dir()]
        except zipfile.BadZipFile as exc:
            raise JobError(f"{plan['first']} is not a valid ZIP archive (corrupt or incomplete "
                           "file)") from exc
        if not infos:
            raise JobError(f"{plan['first']} is an empty archive")
        if len(infos) > LOCAL_FULL_MODE.max_files:
            raise JobError(f"archive has {len(infos):,} entries; the limit is "
                           f"{LOCAL_FULL_MODE.max_files:,}", code="UNSAFE_ARCHIVE")
        return sum(i.file_size for i in infos)

    if plan["kind"] == "multipart_rar":
        for i, f in enumerate(plan["files"], start=1):
            num = _part_number(f["name"])
            try:
                vol = rar_volume_number(upload / f["name"])
            except RarArchiveError as exc:
                raise JobError(f"{f['name']} is not a readable RAR volume (corrupt, incomplete, "
                               "or not a RAR file)") from exc
            if vol != num:
                raise JobError(f"{f['name']} is volume {vol} of its archive according to its own "
                               f"header, not part {num}. The parts look renamed or come from "
                               "different downloads.", code="MISMATCHED_PARTS")
            _update(d, stages={"check": {"done": i, "detail": f"{f['name']}: volume {vol} OK"}})
        if plan.get("missing"):
            return _check_partial(d, plan)
    try:
        entries = list_rar_entries(first)  # 7z lists RAR and 7Z alike, and names a missing volume
    except RarArchiveError as exc:
        msg = str(exc)
        if msg.startswith("missing archive part"):
            raise JobError(f"incomplete multi-part archive: {msg.split(': ', 1)[1]} is required "
                           "but was not uploaded.", code="MISSING_PARTS") from exc
        if "no file entries" in msg:
            raise JobError(f"{plan['first']} is an empty archive") from exc
        if plan["kind"] == "multipart_7z":
            # 7z does not name a missing trailing .7z.NNN volume; it only fails to open.
            raise JobError("the multi-part 7z archive could not be opened: most likely the last "
                           "part is missing (it cannot be detected from file names), or a part "
                           "is corrupt.", code="MISSING_PARTS") from exc
        raise JobError("the archive could not be read (corrupt, incomplete, mismatched parts, or "
                       f"an unsupported format): {_safe_message(exc, d)}") from exc
    try:
        return check_entries(entries, LOCAL_FULL_MODE)
    except RarSecurityError as exc:
        raise JobError(f"archive rejected for safety: {_safe_message(exc, d)}",
                       code="UNSAFE_ARCHIVE") from exc


def _part_number(name: str) -> int:
    return int(_RAR_PART_RE.match(name).group("num"))


def _part_groups(plan: dict) -> list[tuple[int, int]]:
    """Runs of consecutive uploaded part numbers, e.g. parts 2,3,5 -> [(2, 3), (5, 5)]."""
    groups: list[list[int]] = []
    for n in sorted(_part_number(f["name"]) for f in plan["files"]):
        if groups and n == groups[-1][1] + 1:
            groups[-1][1] = n
        else:
            groups.append([n, n])
    return [(a, b) for a, b in groups]


def _check_partial(d: Path, plan: dict) -> int:
    """Incomplete RAR set: read every uploaded volume on its own and work out which
    members lie wholly inside the uploaded parts. Writes partial.json for the worker."""
    upload = d / "upload"
    members: dict[str, dict] = {}
    for f in plan["files"]:
        try:
            listing = list_rar_volume(upload / f["name"])
        except RarArchiveError as exc:
            raise JobError(_safe_message(exc, d)) from exc
        for entry, before, after in listing:
            m = members.setdefault(entry.path, {"entry": entry, "vols": [], "start": False,
                                                "end": False})
            m["vols"].append(_part_number(f["name"]))
            m["start"] |= not before
            m["end"] |= not after
    if not members:
        raise JobError(f"{plan['first']} is an empty archive")
    try:
        total = check_entries([m["entry"] for m in members.values()], LOCAL_FULL_MODE)
    except RarSecurityError as exc:
        raise JobError(f"archive rejected for safety: {_safe_message(exc, d)}",
                       code="UNSAFE_ARCHIVE") from exc
    example = plan["files"][0]["name"]
    incomplete = {}
    for path, m in members.items():
        lo, hi = min(m["vols"]), max(m["vols"])
        if m["start"] and m["end"] and hi - lo + 1 == len(set(m["vols"])):
            continue
        gap = (lo - 1 if not m["start"] else hi + 1 if not m["end"]
               else next(n for n in range(lo, hi) if n not in m["vols"]))
        incomplete[path] = (f"split across {_part_name(example, gap, 'multipart_rar')}, which was "
                            "not uploaded")
    # Members are stored folder by folder, so a missing neighbour part can only cut the first
    # and the last folder of each run of consecutive uploaded parts.
    cut: dict[str, str] = {}
    order = list(members)
    for a, b in _part_groups(plan):
        inside = [p for p in order if any(a <= v <= b for v in members[p]["vols"])]
        if a > 1:
            cut.setdefault(posixpath.dirname(inside[0]),
                           f"some of its recordings are in {_part_name(example, a - 1, 'multipart_rar')} "
                           "or earlier parts, which were not uploaded")
        if b < plan["expected_parts"] or not members[inside[-1]]["end"]:
            cut.setdefault(posixpath.dirname(inside[-1]),
                           f"some of its recordings are in {_part_name(example, b + 1, 'multipart_rar')} "
                           "or later parts, which were not uploaded")
    (d / "partial.json").write_text(json.dumps({"incomplete": incomplete, "cut": cut}))
    return total


def _extract(d: Path, plan: dict, expected_bytes: int) -> None:
    data = d / "data"
    data.mkdir(exist_ok=True)
    first = d / "upload" / plan["first"]
    limit = expected_bytes + 64 * 1024**2
    errors: list[BaseException] = []

    if plan["kind"] == "zip":
        def run_zip() -> None:
            try:
                safe_extract_zip(first, data, LOCAL_FULL_MODE)
            except BaseException as exc:  # noqa: BLE001 - re-raised below as a JobError
                errors.append(exc)
        thread = threading.Thread(target=run_zip, daemon=True)
        thread.start()
        alive = thread.is_alive
    else:
        # A partial RAR set is extracted from the first part of each run of consecutive
        # parts; unrar follows the volumes within a run and stops at the gap.
        firsts = ([next(f["name"] for f in plan["files"] if _part_number(f["name"]) == a)
                   for a, _ in _part_groups(plan)] if plan.get("missing") else [plan["first"]])
        log = open(d / "extract.log", "wb")  # noqa: SIM115 - closed after the loop
        stop, codes, current = threading.Event(), [], []

        def run_extractors() -> None:
            for name in firsts:
                if stop.is_set():
                    return
                current[:] = [subprocess.Popen(extract_command(d / "upload" / name, data),
                                               stdout=log, stderr=subprocess.STDOUT,
                                               stdin=subprocess.DEVNULL)]
                codes.append(current[0].wait())
        thread = threading.Thread(target=run_extractors, daemon=True)
        thread.start()
        alive = thread.is_alive
    started = time.monotonic()
    try:
        while alive():
            time.sleep(2)
            done, count = _dir_bytes(data)
            if done > limit:
                raise JobError("extraction produced more data than the archive declared; stopped "
                               "(archive-bomb guard)", code="UNSAFE_ARCHIVE")
            if time.monotonic() - started > EXTRACT_TIMEOUT_S:
                raise JobError("extraction took longer than the 3-hour limit")
            _update(d, stages={"extract": {"done": done, "detail": f"{count:,} files extracted"}})
    finally:
        if plan["kind"] != "zip":
            stop.set()
            if current and current[0].poll() is None:
                current[0].kill()
            thread.join()
            log.close()
    if plan["kind"] != "zip":
        out = (d / "extract.log").read_text(errors="replace")
        # unrar/7z exit 1 = warning (e.g. bytes after the last volume's end on
        # the real XJTU-SY download); data errors still print one of these.
        bad = ("Program aborted", "CRC failed", "checksum error", "Data Error", "Cannot open")
        if plan.get("missing"):
            _settle_partial(d, data, out)
        elif any(c not in (0, 1) for c in codes) or any(b in out for b in bad):
            tail = " ".join(out.strip().splitlines()[-3:])
            raise JobError("extraction failed (corrupt, truncated or mismatched archive parts): "
                           f"{_safe_message(tail, d)}")
    elif errors:
        if isinstance(errors[0], ZipSecurityError):
            raise JobError(f"archive rejected for safety: {_safe_message(errors[0], d)}",
                           code="UNSAFE_ARCHIVE")
        raise JobError(f"extraction failed: {_safe_message(errors[0], d)}")
    # Defense in depth: never trust an extractor's output unchecked.
    root = data.resolve()
    for p in data.rglob("*"):
        if p.is_symlink():
            raise JobError(f"archive contains a link ({p.relative_to(data)}); rejected",
                           code="UNSAFE_ARCHIVE")
        if root not in p.resolve().parents:
            raise JobError("an archive member resolved outside the extraction folder; rejected",
                           code="UNSAFE_ARCHIVE")


def _settle_partial(d: Path, data: Path, out: str) -> None:
    """unrar reports the members split across a missing part as errors (expected);
    any other damaged member means a corrupt part. Drop the split members."""
    incomplete = json.loads((d / "partial.json").read_text())["incomplete"]
    for line in out.splitlines():
        if (any(b in line for b in ("checksum error", "CRC failed", "Data Error"))
                and not any(p in line for p in incomplete)) or "Program aborted" in line:
            raise JobError("extraction failed: a recording inside the uploaded parts is damaged "
                           f"(corrupt or truncated part): {_safe_message(line.strip(), d)}")
    for p in incomplete:
        (data / p).unlink(missing_ok=True)


def _unwrap(root: Path) -> Path:
    # Archives commonly wrap everything in one top-level folder (XJTU-SY does).
    while True:
        entries = list(root.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            root = entries[0]
        else:
            return root


def _run_files(run) -> list[Path]:
    src = Path(run.source)
    return sorted(p for p in src.iterdir() if p.is_file()) if src.is_dir() else [src]


def _skip_reason(rel: str, display_name: str) -> str:
    low = rel.lower()
    if low.endswith((".pdf", ".txt", ".md", ".doc", ".docx", ".html", ".xlsx", ".json")):
        return "documentation / metadata, not a vibration recording"
    if low.endswith(ARCHIVE_SUFFIXES):
        return "nested archive (not extracted)"
    return f"not read by the {display_name} adapter (not a recording of a recognised bearing run)"


def validation_for(dataset: str, display_name: str, candidates) -> dict:
    """Is RUL on this dataset backed by held-out evaluation? Read from the
    deployed model bundle's own validation numbers, never asserted."""
    skills = {c.name: c.skill_for(dataset) for c in candidates}
    trained = sorted({c.name for c in candidates
                      if any(b.startswith(f"{dataset}:") for b in c.train_bearings)})
    positive = {k: v for k, v in skills.items() if v is not None and v > 0}
    shown = ", ".join(f"{k} {v:+.2f}" for k, v in skills.items() if v is not None) or "none"
    if positive:
        best = max(positive, key=positive.get)
        return {"status": "validated", "skills": skills, "trained_on": trained,
                "note": (f"{display_name}: a model has positive held-out skill on this dataset "
                         f"({best}: {positive[best]:+.2f} life-fraction skill over the no-skill "
                         "baseline). RUL is shown only for bearings where the routing gate finds "
                         "that model applicable (HIGH = available, MEDIUM = experimental).")}
    return {"status": "not_validated", "skills": skills, "trained_on": trained,
            "note": (f"{display_name}: no RULGuard model has shown skill on this dataset in "
                     "held-out evaluation (life-fraction skill vs the no-skill baseline: "
                     f"{shown}). "
                     + ("No model was trained on it. " if not trained else "")
                     + "These results are data inspection: health indicator, degradation stage "
                     "(a severity band, not a fault diagnosis) and applicability. RUL is withheld.")}


def _sanitize(obj: Any, root: Path) -> Any:
    text = json.dumps(_json_clean(obj))
    for prefix in (f"{root}/", str(root)):
        text = text.replace(prefix, "")
    return json.loads(text)


# ---------------------------------------------------------------------------
# Custom (unrecognised) datasets
# ---------------------------------------------------------------------------


def _generic_proposal(data: Path, root: Path, profile: dict) -> dict | None:
    """A column mapping for the user to confirm, or None when nothing looks like a signal.
    One bearing run per folder that directly holds data files. Roles come from column
    names (profiler); a headerless file gets a guess, labelled as one, that skips columns
    which only ever increase (a time or index column)."""
    import numpy as np

    from bearing_pdm.generic import discover_generic_files, read_generic_file

    sample = next((f for f in profile["files"] if f.get("readable")
                   and any(c["numeric"] and not c["constant"] for c in f["columns"])), None)
    rate = None
    if sample is None:
        sample, rate = _signal_sample(root)
    if sample is None:
        return None
    signal_cols = [c for c in sample["columns"] if c["numeric"] and not c["constant"]]
    increasing: set[str] = set()
    if not sample["has_header"]:
        df = read_generic_file(root / sample["relative_path"],
                               sample["delimiter"], sample["has_header"])
        increasing = {c for c in df.columns if len(df) > 2 and bool(
            (np.diff(_numeric(df[c])) > 0).all())}
    columns, guessed = [], 0
    for c in sample["columns"]:
        role = c["canonical"] if c["canonical"] in GENERIC_ROLES else None
        confidence = c["confidence"] if role else "none"
        columns.append({"name": c["name"], "role": role, "confidence": confidence,
                        "usable": c["numeric"]})
    if not any(col["role"] and col["role"].startswith("vibration") for col in columns):
        for col in columns:
            if (any(c["name"] == col["name"] for c in signal_cols) and not col["role"]
                    and col["name"] not in increasing and guessed < 2):
                col.update(role=("vibration_x", "vibration_y")[guessed], confidence="guess")
                guessed += 1
    suffix = Path(sample["relative_path"]).suffix.lower()
    folders: dict[Path, int] = {}
    for f in {p.parent for p in root.rglob("*") if p.is_file()}:
        try:
            folders[f] = len(discover_generic_files(f, suffix))
        except FileNotFoundError:
            continue
    runs = [{"path": f.relative_to(root).as_posix(),
             "id": root.name if f == root else f.relative_to(root).as_posix(), "files": n}
            for f, n in sorted(folders.items())]
    from_time = str(profile.get("sampling_rate_source", "")).startswith("time column")
    return {
        "root": root.relative_to(data).as_posix(),
        "sample_file": sample["relative_path"], "suffix": suffix,
        "delimiter": sample["delimiter"], "has_header": sample["has_header"],
        "rows_per_file": sample["rows"],
        "columns": columns, "roles": list(GENERIC_ROLES), "runs": runs[:200],
        "sampling_rate_hz": rate or (profile["sampling_rate_hz"] if from_time else None),
        "needs_interval": any(r["files"] > 1 for r in runs),
        "warnings": [w for w in profile["warnings"]
                     if "adapter" not in w and "no tabular" not in w][:10],
    }


def _signal_sample(root: Path) -> tuple[dict | None, float | None]:
    """The profiler only reads text tables; for .mat/.wav recordings, the first file that
    opens stands in as the sample, described the way profile_file describes a table.
    A .wav header states its sampling rate; a .mat file is never assumed to."""
    import numpy as np

    from bearing_pdm.generic import SIGNAL_SUFFIXES, read_generic_file, wav_sampling_rate

    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SIGNAL_SUFFIXES)
    for f in files[:20]:
        try:
            df = read_generic_file(f, None, True)
        except Exception:  # noqa: BLE001 - try the next file; none readable -> no proposal
            continue
        cols = [{"name": c, "numeric": True, "constant": bool(np.ptp(df[c].to_numpy()) == 0),
                 "canonical": None, "confidence": "none"} for c in df.columns]
        if not any(not c["constant"] for c in cols):
            continue
        return ({"relative_path": f.relative_to(root).as_posix(), "has_header": True,
                 "delimiter": None, "rows": len(df), "columns": cols},
                wav_sampling_rate(f) if f.suffix.lower() == ".wav" else None)
    return None, None


def _numeric(values):
    import pandas as pd

    return pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)


def submit_mapping(job_id: str, mapping: dict) -> dict:
    """Validate the user's confirmed mapping against the proposal, then resume the job."""
    d = job_dir(job_id)
    state = _read_state(d)
    if state["state"] != "needs_mapping":
        raise JobError(f"job is {state['state']}, not waiting for a column mapping",
                       code="CONFLICT", status=409)
    proposal = state["mapping_proposal"]
    names = {c["name"] for c in proposal["columns"] if c["usable"]}
    columns = {str(k): str(v) for k, v in (mapping.get("columns") or {}).items() if v}
    if set(columns) - names:
        raise JobError(f"unknown or unusable column(s): {sorted(set(columns) - names)[:5]}")
    if set(columns.values()) - set(GENERIC_ROLES):
        raise JobError(f"unknown role(s): {sorted(set(columns.values()) - set(GENERIC_ROLES))}")
    vib = [v for v in columns.values() if v.startswith("vibration")]
    if not vib or len(vib) != len(set(vib)):
        raise JobError("choose one or two vibration columns (each vibration role at most once)")
    rate = mapping.get("sampling_rate_hz")
    if not isinstance(rate, int | float) or not 1 <= rate <= 1_000_000:
        raise JobError("sampling rate must be between 1 Hz and 1,000,000 Hz")
    interval = mapping.get("recording_interval_s")
    if proposal["needs_interval"]:
        if not isinstance(interval, int | float) or not 0 < interval <= 10_000_000:
            raise JobError("time between recordings must be a positive number of seconds")
    else:
        interval = None
    (d / "mapping.json").write_text(json.dumps(
        {"columns": columns, "sampling_rate_hz": float(rate),
         "recording_interval_s": None if interval is None else float(interval),
         "ran_to_failure": mapping.get("ran_to_failure") is True}))
    state.update(state="queued", message="Mapping confirmed. Waiting for the processing worker.")
    state["stages"]["process"].update(status="pending")
    _write_state(d, state)
    pid = _spawn_worker(d, job_id)
    if pid is not None:
        state = _read_state(d)
        state["pid"] = pid
        _write_state(d, state)
    return public_state(d)


def _generic_runs(d: Path, data: Path):
    from bearing_pdm.adapters import ROLE_RUN_TO_FAILURE, GenericAdapter

    proposal = _read_state(d)["mapping_proposal"]
    m = json.loads((d / "mapping.json").read_text())
    adapter = GenericAdapter(mapping=m["columns"], sampling_rate_hz=m["sampling_rate_hz"],
                             delimiter=proposal["delimiter"], has_header=proposal["has_header"],
                             recording_interval_s=m["recording_interval_s"],
                             suffix=proposal["suffix"])
    adapter.display_name = "Custom dataset (your column mapping)"
    root = (data / proposal["root"]).resolve()
    if not root.is_relative_to(data.resolve()):
        raise JobError("invalid dataset root")
    # Only the user's word makes a custom bearing a run-to-failure record: nothing in
    # the files says it failed. With it, the last recording is the failure (pipeline.py).
    rtf = {"run_to_failure": True, "role": ROLE_RUN_TO_FAILURE} if m.get("ran_to_failure") else {}
    runs = [replace(adapter.discover(root / r["path"])[0], bearing_id=r["id"], **rtf)
            for r in proposal["runs"]]
    return root, adapter, runs


def run_job(job_id: str) -> None:
    d = JOBS_ROOT / job_id
    with open(JOBS_ROOT / ".worker.lock", "w") as lock:
        try:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    _update(d, message="Waiting for another dataset job to finish "
                                       "(one runs at a time).")
                    time.sleep(3)
            _run_locked(d)
        except _Cancelled:
            _delete_raw(d)
        except JobError as exc:
            _fail(d, str(exc))
        except MemoryError:
            _fail(d, "Processing ran out of memory on the server.")
        except Exception as exc:  # noqa: BLE001 - logged; the UI gets a path-free message
            print(f"job {job_id} failed: {exc!r}", flush=True)
            _fail(d, f"Processing failed with an internal error: {_safe_message(exc, d)}")


def _run_locked(d: Path) -> None:
    from bearing_pdm.adapters import get_adapter
    from bearing_pdm.profiler import profile_folder

    plan = _read_state(d)["plan"]
    data = d / "data"
    if (d / "mapping.json").is_file():  # resumed after the user confirmed a custom mapping
        root, adapter, runs = _generic_runs(d, data)
        profile = profile_folder(root)
        all_files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        _process(d, data, plan, root, profile, all_files, adapter, "generic", runs, None, [])
        return
    if plan["kind"] != "files":
        _update(d, state="checking", message="Checking the archive parts and contents.",
                stages={"check": {"status": "running", "total": len(plan["files"])}})
        uncompressed = _check_archive(d, plan)
        free = shutil.disk_usage(d).free
        if uncompressed + DISK_MARGIN_BYTES > free:
            raise JobError(f"the archive expands to {uncompressed / 1024**3:.1f} GB, but only "
                           f"{free / 1024**3:.1f} GB of server disk is free. Upload a subset "
                           "(for example one condition folder as a ZIP).")
        _update(d, state="extracting", message="Extracting the archive.",
                stages={"check": {"status": "done", "done": len(plan["files"]),
                                  "detail": f"{len(plan['files'])} part(s) verified, "
                                            f"{uncompressed / 1024**3:.2f} GB uncompressed"},
                        "extract": {"status": "running", "total": uncompressed}})
        _extract(d, plan, uncompressed)
        shutil.rmtree(d / "upload", ignore_errors=True)  # free the disk before processing
        done, count = _dir_bytes(data)
        _update(d, stages={"extract": {"status": "done", "done": done,
                                       "detail": f"{count:,} files extracted"}})

    _update(d, state="detecting", message="Detecting the dataset format.",
            stages={"detect": {"status": "running"}})
    if not data.is_dir() or not any(p.is_file() for p in data.rglob("*")):
        raise JobError("the upload contains no files (empty archive or only folders)")
    root = _unwrap(data)
    profile = profile_folder(root)
    all_files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    known = [k["dataset_id"] for k in profile["known_datasets"]]
    proposal = None if known else _generic_proposal(data, root, profile)
    if proposal:
        _update(d, state="needs_mapping", mapping_proposal=proposal,
                message="Format not recognised as a known dataset. Confirm which columns are "
                        "vibration, the sampling rate and the time between recordings to analyse it.",
                stages={"detect": {"status": "done",
                                   "detail": f"custom format, {len(proposal['runs'])} bearing "
                                             "run(s) proposed: waiting for your confirmation"}})
        return
    if not known:
        summary = {"dataset_id": None, "display_name": None,
                   "files_found": len(all_files), "files_processed": 0,
                   "files_skipped": len(all_files), "files_failed": 0,
                   "bearings_found": 0, "bearings_processed": 0, "bearings_failed": 0,
                   "skipped": [{"path": p, "reason": "dataset format not recognised"}
                               for p in all_files[:200]], "failed": []}
        result = {"outcome": "profile_only", "dataset_id": None,
                  "profile": _sanitize(profile, root), "decisions": {}, "trajectories": {},
                  "validation": None, "summary": summary}
        (d / "result.json").write_text(json.dumps(_json_clean(result)))
        _update(d, state="completed", summary=summary,
                message="Inspected only: the files were profiled, but no supported dataset format "
                        "was recognised, so no bearing analysis was run.",
                stages={"detect": {"status": "done", "detail": "format not recognised"},
                        "process": {"status": "skipped", "detail": "nothing to process"}})
        _delete_raw(d)
        return

    dataset = known[0]
    adapter = get_adapter(dataset)
    runs, level = None, root
    while runs is None:
        try:
            runs = adapter.discover(level)
        except (FileNotFoundError, ValueError) as exc:
            # Unwrapping can go one folder too deep: a partial XJTU-SY set holds a single
            # condition folder, but the adapter expects condition folders under its root.
            if level == data:
                raise JobError(f"recognised as {adapter.display_name}, but no bearing runs were "
                               f"found: {_safe_message(exc, d)}") from exc
            level = level.parent
    if level != root:
        root, profile = level, profile_folder(level)
        all_files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    partial = json.loads((d / "partial.json").read_text()) if plan.get("missing") else None
    cut_runs = []
    if partial:
        # A bearing cut by a missing part has no known end of life: censor it, as
        # build_canonical_features does for any run that is not run-to-failure.
        droot = data.resolve()
        for i, r in enumerate(runs):
            reason = partial["cut"].get(Path(r.source).resolve().relative_to(droot).as_posix())
            if reason:
                cut_runs.append({"bearing": r.run_id, "reason": reason})
                runs[i] = replace(r, run_to_failure=False)
    _process(d, data, plan, root, profile, all_files, adapter, dataset, runs, partial, cut_runs)


def _process(d: Path, data: Path, plan: dict, root: Path, profile: dict, all_files: list[str],
             adapter, dataset: str, runs: list, partial: dict | None, cut_runs: list) -> None:
    import joblib
    import pandas as pd

    from bearing_pdm.health import health_quality
    from bearing_pdm.pipeline import build_canonical_features
    from bearing_pdm.routing import candidates_from_bundle, oof_from_predictions, route_dataset
    from bearing_pdm.upload_rul import dataset_rul

    run_files = {r.run_id: _run_files(r) for r in runs}
    _update(d, state="processing",
            message=f"Recognised {adapter.display_name}: {len(runs)} bearing run(s). Extracting "
                    "features from every recording.",
            stages={"detect": {"status": "done",
                               "detail": f"{adapter.display_name}, {len(runs)} bearing run(s)"},
                    "process": {"status": "running",
                                "total": sum(len(v) for v in run_files.values())}})

    counter = {"n": 0, "last": 0.0}

    class _Counting:  # adapter proxy: per-recording progress, same recordings
        def recordings(self, run):
            for rec in adapter.recordings(run):
                counter["n"] += 1
                if time.monotonic() - counter["last"] > 2:
                    counter["last"] = time.monotonic()
                    _update(d, stages={"process": {"done": counter["n"],
                                                   "detail": f"{run.run_id}: {rec.recording_id}"}})
                yield rec

    frames, failed_runs, processed = [], [], set()
    rroot = root.resolve()
    for run in runs:
        try:
            df = build_canonical_features(_Counting(), run)
        except _Cancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad bearing must not hide the others
            failed_runs.append({"bearing": run.run_id, "files": len(run_files[run.run_id]),
                                "reason": _safe_message(exc, d)})
            continue
        if df.empty:
            failed_runs.append({"bearing": run.run_id, "files": len(run_files[run.run_id]),
                                "reason": "no recordings found"})
            continue
        frames.append(df)
        processed.update(Path(p).resolve().relative_to(rroot).as_posix()
                         for p in df["source_file_path"])
    failed_ids = {f["bearing"] for f in failed_runs}
    failed_files = {p.resolve().relative_to(rroot).as_posix()
                    for rid, files in run_files.items() if rid in failed_ids for p in files}
    skipped = [p for p in all_files if p not in processed and p not in failed_files]
    if not frames:
        raise JobError("no bearing run could be processed: "
                       + "; ".join(f"{f['bearing']}: {f['reason']}" for f in failed_runs[:5]))

    _update(d, message="Routing every bearing: health indicator, stages, applicability, RUL gate.",
            stages={"process": {"done": counter["n"], "detail": "loading the routing models"}})
    bundle = joblib.load(REPO_ROOT / "artifacts" / "models" / "cross_domain_bundle.joblib")
    pred_path = REPO_ROOT / "reports" / "metrics" / "cross_dataset_predictions.parquet"
    oof = oof_from_predictions(pd.read_parquet(pred_path)) if pred_path.exists() else None
    _, decisions, trajectories = route_dataset(
        pd.concat(frames, ignore_index=True), dataset, bundle, oof=oof,
        progress=lambda msg: _update(d, stages={"process": {"detail": msg[:200]}}),
        adapter=adapter)
    validation = validation_for(dataset, adapter.display_name, candidates_from_bundle(bundle))
    _update(d, message="Testing RUL on this dataset: each run-to-failure bearing is predicted "
                       "by a model trained on the others.")
    rul = dataset_rul(frames, adapter.reference_window,
                      list(bundle["raw_seconds"]["model"].feature_columns),
                      progress=lambda msg: _update(d, stages={"process": {"detail": msg[:200]}}))
    rul["ends_healthy"] = sorted(b for b, t in trajectories.items()
                                 if t and t[0].get("actual_rul_seconds") is not None
                                 and t[-1].get("stage") == "HEALTHY")
    split = []
    if partial:
        wrap = root.relative_to(data).as_posix()
        split = [{"path": p.removeprefix(f"{wrap}/") if wrap != "." else p, "reason": reason}
                 for p, reason in partial["incomplete"].items()]
    summary = {
        "dataset_id": dataset, "display_name": adapter.display_name,
        "files_found": len(all_files) + len(split), "files_processed": len(processed),
        "files_skipped": len(skipped) + len(split), "files_failed": len(failed_files),
        "bearings_found": len(runs), "bearings_processed": len(frames),
        "bearings_failed": len(failed_runs),
        "skipped": split + [{"path": p, "reason": _skip_reason(p, adapter.display_name)}
                            for p in skipped[:200]],
        "failed": failed_runs,
    }
    if partial:
        summary["partial_set"] = {"uploaded": [f["name"] for f in plan["files"]],
                                  "missing": plan["missing"], "incomplete_bearings": cut_runs}
    result = {"outcome": "analyzed", "dataset_id": dataset,
              "profile": _sanitize(profile, root), "decisions": _sanitize(decisions, root),
              "trajectories": trajectories, "validation": validation, "summary": summary,
              "health_quality": health_quality(trajectories), "dataset_rul": rul}
    (d / "result.json").write_text(json.dumps(_json_clean(result)))
    if failed_runs:
        message = (f"Partially completed: {len(failed_runs)} of {len(runs)} bearing run(s) could "
                   "not be processed; the results cover the others only.")
    else:
        message = f"Completed: all {len(runs)} bearing run(s) processed."
    if partial:
        message += (f" Partial dataset: {len(plan['files'])} of {plan['expected_parts']} archive "
                    "parts uploaded, so this covers only the recordings stored in them; "
                    f"{len(cut_runs)} bearing run(s) are incomplete (no end-of-life label). "
                    "Upload every part to analyse the whole dataset.")
    _update(d, state="partial" if failed_runs or partial else "completed", summary=summary,
            validation=validation, message=message,
            stages={"process": {"status": "partial" if failed_runs else "done",
                                "done": len(processed), "detail": ""}})
    _delete_raw(d)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        run_job(sys.argv[2])
    else:
        print("usage: python -m bearing_pdm.dataset_jobs run <job_id>")
        sys.exit(2)
