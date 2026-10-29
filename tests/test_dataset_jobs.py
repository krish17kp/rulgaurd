"""Whole-dataset upload jobs (dataset_jobs.py + /jobs API routes).

Fixtures are synthetic (tests/_xjtu_fixture.py): they exercise the archive /
upload / processing machinery, NOT the real XJTU-SY dataset. The real-archive
tests at the bottom run only where the real download exists locally.
"""

import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import pytest

from _xjtu_fixture import make_xjtu_tree
from bearing_pdm import dataset_jobs as dj

REPO = Path(__file__).resolve().parents[1]
BUNDLE = REPO / "artifacts" / "models" / "cross_domain_bundle.joblib"
needs_bundle = pytest.mark.skipif(not BUNDLE.exists(), reason="cross_domain_bundle.joblib absent")
needs_7z = pytest.mark.skipif(shutil.which("7z") is None, reason="7z not installed")
REAL_XJTU = Path.home() / "Downloads" / "XJTU_parts" / "Data"
needs_real = pytest.mark.skipif(not (REAL_XJTU / "XJTU-SY_Bearing_Datasets.part06.rar").exists(),
                                reason="real XJTU-SY download not present")


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(dj, "JOBS_ROOT", tmp_path / "jobs")
    # Run the worker in-process instead of a detached subprocess.
    monkeypatch.setattr(dj, "_spawn_worker", lambda d, job_id: dj.run_job(job_id))
    return tmp_path


def _zip_tree(src: Path, out: Path) -> Path:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src).as_posix())
    return out


def _submit(paths: list[Path], names: list[str] | None = None, chunk=200_000) -> dict:
    names = names or [p.name for p in paths]
    job = dj.create_job([{"name": n, "size": p.stat().st_size}
                         for n, p in zip(names, paths, strict=True)])
    plan = dj._read_state(dj.JOBS_ROOT / job["id"])["plan"]
    order = {f["name"]: i for i, f in enumerate(plan["files"])}
    for n, p in zip(names, paths, strict=True):
        idx = order[dj._safe_relpath(n) if plan["kind"] == "files" else Path(n).name]
        data, off = p.read_bytes(), 0
        while off < len(data):
            off = dj.append_chunk(job["id"], idx, off, data[off:off + chunk])
    return dj.start_job(job["id"])


# --------------------------------------------------------------------------- planning


@pytest.mark.parametrize("selected, missing", [
    ([5], "XJTU-SY_Bearing_Datasets.part01.rar, XJTU-SY_Bearing_Datasets.part02.rar, "
          "XJTU-SY_Bearing_Datasets.part03.rar, XJTU-SY_Bearing_Datasets.part04.rar, "
          "XJTU-SY_Bearing_Datasets.part06.rar"),
    ([1, 2, 3, 5, 6], "XJTU-SY_Bearing_Datasets.part04.rar"),
    ([2, 3, 4, 5, 6], "XJTU-SY_Bearing_Datasets.part01.rar"),
    ([1, 2, 3, 4, 5], "XJTU-SY_Bearing_Datasets.part06.rar"),
])
def test_incomplete_xjtu_set_is_refused_with_the_missing_parts_named(selected, missing):
    files = [{"name": f"XJTU-SY_Bearing_Datasets.part{n:02d}.rar", "size": 10} for n in selected]
    with pytest.raises(dj.JobError) as e:
        dj.plan_upload(files)
    assert e.value.code == "MISSING_PARTS"
    assert f"missing {missing}." in str(e.value)
    assert "6 parts" in str(e.value)


def test_complete_unknown_set_plans_in_part_order_with_header_check_note():
    plan = dj.plan_upload([{"name": f"set.part{n}.rar", "size": 10} for n in (3, 1, 2)])
    assert plan["kind"] == "multipart_rar"
    assert [f["name"] for f in plan["files"]] == ["set.part1.rar", "set.part2.rar", "set.part3.rar"]
    assert plan["first"] == "set.part1.rar"
    assert "headers" in plan["notes"][0]


def test_unknown_set_missing_middle_part():
    with pytest.raises(dj.JobError, match=r"missing set\.part03\.rar"):
        dj.plan_upload([{"name": f"set.part{n:02d}.rar", "size": 9} for n in (1, 2, 4)])


@pytest.mark.parametrize("files, match", [
    ([{"name": "a.part01.rar", "size": 1}, {"name": "a.part1.rar", "size": 1}], "twice"),
    ([{"name": "a.part01.rar", "size": 1}, {"name": "b.part02.rar", "size": 1}], "different archives"),
    ([{"name": "a.zip", "size": 1}, {"name": "b.csv", "size": 1}], "together"),
    ([{"name": "a.zip", "size": 1}, {"name": "b.zip", "size": 1}], "one archive"),
    ([{"name": "data.z01", "size": 1}], "not supported"),
    ([{"name": "data.r00", "size": 1}], "not supported"),
    ([{"name": "../../etc/passwd", "size": 1}], "unsafe"),
    ([{"name": "/abs/x.csv", "size": 1}], "unsafe"),
    ([{"name": "empty.zip", "size": 0}], "empty"),
    ([{"name": "x.csv", "size": -1}], "invalid size"),
    ([], "no files"),
])
def test_bad_selections_are_refused(files, match):
    with pytest.raises(dj.JobError, match=match):
        dj.plan_upload(files)


def test_oversized_selection_is_refused():
    with pytest.raises(dj.JobError) as e:
        dj.plan_upload([{"name": "big.zip", "size": dj.MAX_JOB_BYTES + 1}])
    assert e.value.status == 413


def test_folder_upload_keeps_relative_paths():
    plan = dj.plan_upload([{"name": "root/35Hz12kN/Bearing1_1/2.csv", "size": 5},
                           {"name": "root/35Hz12kN/Bearing1_1/1.csv", "size": 5}])
    assert plan["kind"] == "files"
    assert [f["name"] for f in plan["files"]] == ["root/35Hz12kN/Bearing1_1/1.csv",
                                                  "root/35Hz12kN/Bearing1_1/2.csv"]


# --------------------------------------------------------------------------- upload protocol


def test_chunk_protocol_rejects_wrong_offset_oversize_and_early_start(jobs):
    job = dj.create_job([{"name": "x.zip", "size": 10}])
    with pytest.raises(dj.JobError) as e:
        dj.append_chunk(job["id"], 0, 5, b"abc")
    assert e.value.code == "OFFSET_MISMATCH"
    assert dj.append_chunk(job["id"], 0, 0, b"abcd") == 4
    assert dj.file_offset(job["id"], 0) == 4  # resume point after an interruption
    with pytest.raises(dj.JobError, match="past the declared"):
        dj.append_chunk(job["id"], 0, 4, b"x" * 7)
    with pytest.raises(dj.JobError) as e:
        dj.start_job(job["id"])
    assert e.value.code == "UPLOAD_INCOMPLETE"
    with pytest.raises(dj.JobError) as e:
        dj.append_chunk(job["id"], 3, 0, b"x")
    assert e.value.status == 404
    with pytest.raises(dj.JobError) as e:
        dj.job_dir("../../etc")
    assert e.value.status == 404


def test_open_job_limit(jobs):
    for _ in range(dj.MAX_OPEN_JOBS):
        dj.create_job([{"name": "x.zip", "size": 10}])
    with pytest.raises(dj.JobError) as e:
        dj.create_job([{"name": "x.zip", "size": 10}])
    assert e.value.code == "BUSY"


def test_disk_space_is_checked_before_upload(jobs, monkeypatch):
    monkeypatch.setattr(dj.shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(10, 10, 1024))
    with pytest.raises(dj.JobError) as e:
        dj.create_job([{"name": "x.zip", "size": 10}])
    assert e.value.code == "INSUFFICIENT_STORAGE"


def test_abandoned_upload_is_swept(jobs):
    job = dj.create_job([{"name": "x.zip", "size": 10}])
    dj.append_chunk(job["id"], 0, 0, b"abc")
    d = dj.JOBS_ROOT / job["id"]
    old = time.time() - dj.INCOMPLETE_TTL_S - 10
    state = dj._read_state(d)
    state["updated_at"] = old
    (d / "state.json").write_text(json.dumps(state))
    for p in d.rglob("*"):
        os.utime(p, (old, old))
    dj.sweep()
    assert not d.exists()


def test_cancel_deletes_uploaded_bytes(jobs):
    job = dj.create_job([{"name": "x.zip", "size": 10}])
    dj.append_chunk(job["id"], 0, 0, b"abc")
    assert dj.cancel_job(job["id"])["state"] == "cancelled"
    assert not (dj.JOBS_ROOT / job["id"] / "upload").exists()


def test_lost_worker_is_reported_as_interrupted(jobs):
    job = dj.create_job([{"name": "x.zip", "size": 3}])
    d = dj.JOBS_ROOT / job["id"]
    state = dj._read_state(d)
    state.update(state="processing", pid=999_999)  # no such process
    dj._write_state(d, state)
    out = dj.public_state(d)
    assert out["state"] == "failed"
    assert "interrupted" in out["message"]


# --------------------------------------------------------------------------- processing


@needs_bundle
def test_zip_with_nested_folders_processes_every_bearing(jobs):
    src = jobs / "src"
    make_xjtu_tree(src, bearings=("Bearing1_1", "Bearing1_2", "Bearing1_3"))
    out = _submit([_zip_tree(src, jobs / "xjtu.zip")])
    assert out["state"] == "completed", out["message"]
    s = out["summary"]
    assert (s["bearings_found"], s["bearings_processed"], s["bearings_failed"]) == (3, 3, 0)
    assert (s["files_found"], s["files_processed"], s["files_skipped"]) == (43, 42, 1)
    assert s["skipped"] == [{"path": "Introduction.pdf",
                             "reason": "documentation / metadata, not a vibration recording"}]
    # Model honesty comes from the deployed bundle's own held-out numbers.
    assert out["validation"]["status"] == "not_validated"
    result = dj.read_result(out["id"])
    assert all(d["status"] == "RUL_SUPPRESSED" for d in result["decisions"].values())
    traj = result["trajectories"]["xjtu:Bearing1_1"]
    assert [p["sequence_index"] for p in traj] == list(range(14))  # numeric file order
    assert all(p["predicted_rul_seconds"] is None for p in traj)
    assert str(jobs) not in json.dumps(result) + json.dumps(out)  # no server paths
    assert sorted(p.name for p in (dj.JOBS_ROOT / out["id"]).iterdir()) == [
        "result.json", "state.json"]  # raw upload and extraction deleted


@needs_bundle
@needs_7z
def test_multipart_7z_set_extracts_and_processes(jobs):
    src = jobs / "src"
    base = make_xjtu_tree(src)
    subprocess.run(["7z", "a", "-v300k", "-mx=1", str(jobs / "set.7z"), str(base)],
                   check=True, capture_output=True)
    parts = sorted(jobs.glob("set.7z.*"))
    assert len(parts) >= 3
    out = _submit(parts)
    assert out["state"] == "completed", out["message"]
    assert out["summary"]["bearings_processed"] == 2


@needs_7z
def test_multipart_7z_missing_last_part_fails_at_check(jobs):
    base = make_xjtu_tree(jobs / "src")
    subprocess.run(["7z", "a", "-v300k", "-mx=1", str(jobs / "set.7z"), str(base)],
                   check=True, capture_output=True)
    out = _submit(sorted(jobs.glob("set.7z.*"))[:-1])
    assert out["state"] == "failed"
    assert "last part is missing" in out["message"]
    assert out["stages"]["check"]["status"] == "failed"
    assert not (dj.JOBS_ROOT / out["id"] / "upload").exists()


@needs_7z
def test_corrupt_archive_fails_with_a_readable_message(jobs):
    bad = jobs / "broken.7z"
    bad.write_bytes(os.urandom(5000))
    out = _submit([bad])
    assert out["state"] == "failed"
    assert "could not be read" in out["message"]
    assert str(jobs) not in out["message"]


def test_truncated_zip_fails(jobs):
    make_xjtu_tree(jobs / "src", n_files=3)
    z = _zip_tree(jobs / "src", jobs / "x.zip")
    cut = jobs / "cut.zip"
    cut.write_bytes(z.read_bytes()[: z.stat().st_size // 2])
    out = _submit([cut])
    assert out["state"] == "failed"
    assert "not a valid ZIP" in out["message"]


def test_empty_zip_fails(jobs):
    z = jobs / "empty.zip"
    with zipfile.ZipFile(z, "w"):
        pass
    out = _submit([z])
    assert out["state"] == "failed"
    assert "empty" in out["message"]


def test_path_traversal_zip_is_rejected(jobs):
    z = jobs / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../../escape.csv", "a,b\n1,2\n")
    out = _submit([z])
    assert out["state"] == "failed"
    assert "safety" in out["message"]
    assert not (jobs / "escape.csv").exists()


def test_zip_bomb_ratio_is_rejected(jobs):
    z = jobs / "bomb.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.csv", b"0" * (20 * 1024 * 1024))
    out = _submit([z])
    assert out["state"] == "failed"
    assert "bomb" in out["message"]


@needs_bundle
def test_one_corrupt_bearing_gives_partial_not_complete(jobs):
    base = make_xjtu_tree(jobs / "src")
    (base / "35Hz12kN" / "Bearing1_2" / "7.csv").write_text("wrong,header\n1,2\n")
    out = _submit([_zip_tree(jobs / "src", jobs / "x.zip")])
    assert out["state"] == "partial"
    s = out["summary"]
    assert (s["bearings_processed"], s["bearings_failed"]) == (1, 1)
    assert s["failed"][0]["bearing"] == "xjtu:Bearing1_2"
    assert "unexpected header" in s["failed"][0]["reason"]
    assert s["files_failed"] == 14
    assert str(jobs) not in json.dumps(out)


@needs_bundle
def test_folder_upload_of_loose_files(jobs):
    base = make_xjtu_tree(jobs / "src")
    files = sorted(p for p in base.rglob("*") if p.is_file())
    out = _submit(files, [p.relative_to(jobs / "src").as_posix() for p in files])
    assert out["state"] == "completed", out["message"]
    assert out["stages"]["extract"]["status"] == "skipped"
    assert out["summary"]["files_processed"] == 28


def test_unrecognised_data_is_inspection_only(jobs):
    (jobs / "src" / "misc").mkdir(parents=True)
    (jobs / "src" / "misc" / "notes.txt").write_text("hello")
    out = _submit([_zip_tree(jobs / "src", jobs / "misc.zip")])
    assert out["state"] == "completed"
    assert out["message"].startswith("Inspected only")
    assert dj.read_result(out["id"])["outcome"] == "profile_only"


# --------------------------------------------------------------------------- API + real worker


@needs_bundle
def test_api_round_trip_with_detached_worker_and_resume(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from bearing_pdm.api import app

    monkeypatch.setattr(dj, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setenv("PYTHONPATH", str(REPO / "src"))
    make_xjtu_tree(tmp_path / "src")
    data = _zip_tree(tmp_path / "src", tmp_path / "x.zip").read_bytes()
    client = TestClient(app)
    r = client.post("/jobs", json={"files": [{"name": "x.zip", "size": len(data)}]})
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    half = len(data) // 2
    assert client.post(f"/jobs/{job_id}/files/0?offset=0",
                       content=data[:half]).json() == {"received": half}
    bad = client.post(f"/jobs/{job_id}/files/0?offset=0", content=data[half:])
    assert bad.status_code == 409 and bad.json()["code"] == "OFFSET_MISMATCH"
    resume = client.get(f"/jobs/{job_id}/files/0").json()["received"]
    client.post(f"/jobs/{job_id}/files/0?offset={resume}", content=data[resume:])
    assert client.post(f"/jobs/{job_id}/start").status_code == 200
    client = TestClient(app)  # a fresh client, as after a page refresh
    deadline = time.time() + 120
    while time.time() < deadline:
        state = client.get(f"/jobs/{job_id}").json()
        if state["state"] in dj.TERMINAL:
            break
        time.sleep(1)
    assert state["state"] == "completed", state
    result = client.get(f"/jobs/{job_id}/result").json()
    assert set(result["decisions"]) == {"xjtu:Bearing1_1", "xjtu:Bearing1_2"}
    assert client.get("/jobs/not-a-real-job-id-xx").status_code == 404


def test_api_refuses_part05_alone():
    from fastapi.testclient import TestClient

    from bearing_pdm.api import app

    r = TestClient(app).post("/jobs", json={"files": [
        {"name": "XJTU-SY_Bearing_Datasets.part05.rar", "size": 744488960}]})
    assert r.status_code == 400
    assert r.json()["code"] == "MISSING_PARTS"
    assert "part01" in r.json()["message"]


# --------------------------------------------------------------------------- real XJTU-SY parts


def _job_with_links(tmp_path, links: dict[str, Path]) -> Path:
    d = tmp_path / "job"
    (d / "upload").mkdir(parents=True, exist_ok=True)
    for name, target in links.items():
        (d / "upload" / name).unlink(missing_ok=True)
        (d / "upload" / name).symlink_to(target)
    (d / "state.json").write_text(json.dumps({"state": "checking", "stages": {"check": {}}}))
    return d


@needs_real
def test_real_xjtu_parts_header_volumes_and_listing(tmp_path, monkeypatch):
    """Header check of the real 6-part download (fast: lists, does not extract)."""
    monkeypatch.setattr(dj, "JOBS_ROOT", tmp_path)
    parts = [REAL_XJTU / f"XJTU-SY_Bearing_Datasets.part{n:02d}.rar" for n in range(1, 7)]
    d = _job_with_links(tmp_path, {p.name: p for p in parts})
    plan = dj.plan_upload([{"name": p.name, "size": p.stat().st_size} for p in parts])
    assert dj._check_archive(d, plan) == 12_220_812_451


@needs_real
def test_real_xjtu_missing_last_part_and_swapped_parts(tmp_path, monkeypatch):
    monkeypatch.setattr(dj, "JOBS_ROOT", tmp_path)
    real = {n: REAL_XJTU / f"XJTU-SY_Bearing_Datasets.part{n:02d}.rar" for n in range(1, 7)}
    # Renamed as an unknown 5-part set so the name check passes; the headers must catch it.
    d = _job_with_links(tmp_path, {f"set.part{n}.rar": real[n] for n in range(1, 6)})
    plan = dj.plan_upload([{"name": f"set.part{n}.rar", "size": 1} for n in range(1, 6)])
    with pytest.raises(dj.JobError) as e:
        dj._check_archive(d, plan)
    assert e.value.code == "MISSING_PARTS"
    assert "set.part6.rar is required" in str(e.value)
    d = _job_with_links(tmp_path, {"set.part2.rar": real[3], "set.part3.rar": real[2]})
    with pytest.raises(dj.JobError) as e:
        dj._check_archive(d, plan)
    assert e.value.code == "MISMATCHED_PARTS"


def test_api_plan_is_a_dry_run(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from bearing_pdm.api import app

    monkeypatch.setattr(dj, "JOBS_ROOT", tmp_path / "jobs")
    files = [{"name": f"XJTU-SY_Bearing_Datasets.part{n:02d}.rar", "size": 744488960}
             for n in (6, 2, 1, 3, 5, 4)]
    r = TestClient(app).post("/jobs/plan", json={"files": files})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "multipart_rar"
    assert body["first"] == "XJTU-SY_Bearing_Datasets.part01.rar"
    assert [f["name"][-10:] for f in body["files"]] == [f"part0{n}.rar" for n in range(1, 7)]
    assert not (tmp_path / "jobs").exists()
