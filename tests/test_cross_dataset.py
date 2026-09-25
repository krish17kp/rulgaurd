"""Adapters, canonical format, sampling-rate handling and the profiler.

Real fixture bytes where they exist (data/fixtures/); IMS and XJTU-SY are not
committed, so their tests write tiny files in the exact published layout.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bearing_pdm.adapters import ADAPTERS, get_adapter
from bearing_pdm.features import signal_quality
from bearing_pdm.femto import discover_femto_bearings
from bearing_pdm.health import candidate_feature_columns
from bearing_pdm.pipeline import (
    build_canonical_features,
    build_femto_feature_rows,
    canonical_feature_row,
)
from bearing_pdm.profiler import detect_datasets, map_column, profile_file, profile_folder

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def _write_ims(root: Path, n_files: int = 3, n_rows: int = 2048) -> None:
    rng = np.random.default_rng(0)
    for test, folder, n_cols in (("1", "1st_test", 8), ("2", "2nd_test", 4)):
        d = root / folder
        d.mkdir(parents=True)
        for i in range(n_files):
            name = f"2004.02.12.10.{i * 10:02d}.39"
            data = rng.normal(0, 0.1, size=(n_rows, n_cols))
            np.savetxt(d / name, data, fmt="%.3f", delimiter="\t")


def _write_xjtu(root: Path, n_files: int = 12, n_rows: int = 4096) -> Path:
    rng = np.random.default_rng(1)
    bearing = root / "37.5Hz11kN" / "Bearing2_1"
    bearing.mkdir(parents=True)
    for i in range(1, n_files + 1):
        pd.DataFrame({"Horizontal_vibration_signals": rng.normal(0, 0.5, n_rows),
                      "Vertical_vibration_signals": rng.normal(0, 0.5, n_rows)}
                     ).to_csv(bearing / f"{i}.csv", index=False)
    return bearing


# ---------------------------------------------------------------------------
# Adapters and canonical schema
# ---------------------------------------------------------------------------

def test_registry_covers_four_datasets_and_rejects_unknown():
    assert set(ADAPTERS) == {"femto", "college", "ims", "xjtu"}
    with pytest.raises(ValueError, match="Unknown dataset"):
        get_adapter("cwru")


def test_femto_canonical_rows_equal_the_legacy_pipeline():
    """The frozen FEMTO model must see identical inputs through the adapter path."""
    adapter = get_adapter("femto")
    run = adapter.discover(FIXTURES / "femto")[0]
    canonical = build_canonical_features(adapter, run)
    legacy = pd.DataFrame(list(build_femto_feature_rows(
        discover_femto_bearings(FIXTURES / "femto", "learning")[0])))
    shared = [c for c in legacy.columns if c.startswith(("vibration_", "bearing_temp_"))]
    assert len(shared) == 49
    np.testing.assert_allclose(canonical[shared].to_numpy(float), legacy[shared].to_numpy(float),
                               equal_nan=True)
    assert canonical["n_windows"].eq(1).all()          # 2560 samples = one 0.1 s window
    assert canonical["rpm"].eq(1800).all() and canonical["radial_load_n"].eq(4000).all()


def test_femto_adapter_rejects_bearing_folders_without_acquisitions(tmp_path):
    """XJTU-SY uses the same BearingC_N names - a name alone is not FEMTO."""
    (tmp_path / "Bearing1_1").mkdir()
    (tmp_path / "Bearing1_1" / "1.csv").write_text("a,b\n1,2\n")
    assert get_adapter("femto").discover(tmp_path) == []


def test_college_adapter_reads_fixture_with_nan_preserved(tmp_path):
    src = FIXTURES / "college" / "LogFile_2022-06-20-17-00-31_head5000.csv"
    shutil.copy(src, tmp_path / "LogFile_2022-06-20-17-00-31.csv")
    shutil.copy(FIXTURES / "college" / "LogFile_2022-06-26-01-00-31_tail5000.csv",
                tmp_path / "LogFile_2022-06-20-18-00-31.csv")
    adapter = get_adapter("college")
    run = adapter.discover(tmp_path)[0]
    recs = list(adapter.recordings(run))
    assert [r.elapsed_s for r in recs] == [0.0, 3600.0]
    assert set(recs[0].signals) == {"vibration_x", "vibration_y", "temperature_bearing",
                                    "temperature_ambient"}
    df = build_canonical_features(adapter, run)
    assert list(df["rul_seconds"]) == [3600.0, 0.0]
    assert df["bearing_minus_ambient_temp_mean"].notna().all()


def test_ims_adapter_channel_layout_and_failure_labels(tmp_path):
    _write_ims(tmp_path)
    adapter = get_adapter("ims")
    runs = {r.bearing_id: r for r in adapter.discover(tmp_path)}
    assert len(runs) == 8                                   # 4 bearings x tests 1 and 2
    assert runs["test1_bearing3"].run_to_failure and runs["test1_bearing3"].role == "run_to_failure"
    assert not runs["test1_bearing1"].run_to_failure and runs["test1_bearing1"].role == "survivor"
    rec = next(adapter.recordings(runs["test1_bearing3"]))
    assert set(rec.signals) == {"vibration_x", "vibration_y"}   # two accelerometers in test 1
    rec2 = next(adapter.recordings(runs["test2_bearing1"]))
    assert set(rec2.signals) == {"vibration_x"}                 # one accelerometer in test 2
    surv = build_canonical_features(adapter, runs["test2_bearing2"])
    assert surv["rul_seconds"].isna().all()                     # no end of life -> no label


def test_ims_missing_channel_yields_nan_features_not_zero(tmp_path):
    _write_ims(tmp_path)
    adapter = get_adapter("ims")
    run = [r for r in adapter.discover(tmp_path) if r.bearing_id == "test2_bearing1"][0]
    row = canonical_feature_row(next(adapter.recordings(run)))
    assert np.isnan(row["vibration_y_rms"]) and np.isfinite(row["vibration_x_rms"])
    assert row["qc_vibration_y_constant"] == 1.0


def test_xjtu_adapter_numeric_file_order_and_rul(tmp_path):
    _write_xjtu(tmp_path)
    adapter = get_adapter("xjtu")
    run = adapter.discover(tmp_path)[0]
    assert (run.rpm, run.radial_load_n) == (2250.0, 11000.0)
    df = build_canonical_features(adapter, run)
    assert list(df["recording_id"][:3]) == ["1.csv", "2.csv", "3.csv"]
    assert df["recording_id"].iloc[-1] == "12.csv"          # 12 after 9, not after 1
    assert df["rul_seconds"].iloc[0] == 11 * 60.0 and df["rul_seconds"].iloc[-1] == 0.0
    assert df["life_fraction"].is_monotonic_increasing


def test_canonical_metadata_never_becomes_a_feature(tmp_path):
    _write_xjtu(tmp_path)
    adapter = get_adapter("xjtu")
    df = build_canonical_features(adapter, adapter.discover(tmp_path)[0])
    cols = candidate_feature_columns(df)
    forbidden = {"elapsed_s", "life_fraction", "rul_seconds", "rpm", "radial_load_n",
                 "sequence_index", "sample_rate_hz", "n_windows"}
    assert not forbidden & set(cols)
    assert not [c for c in cols if c.startswith("qc_")]


# ---------------------------------------------------------------------------
# Sampling rate / FFT / fixed-duration windows
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fs", [20_000.0, 25_600.0])
def test_fft_uses_the_real_sampling_rate(fs):
    """A 1 kHz tone must read as 1 kHz at 20 kHz (IMS) and 25.6 kHz (FEMTO)."""
    from bearing_pdm.adapters import BearingRun, Recording
    t = np.arange(int(fs)) / fs
    run = BearingRun("x", "b", "learning", Path("."), fs, True)
    rec = Recording(run, "r", 0, 0.0, Path("r"), {"vibration_x": np.sin(2 * np.pi * 1000 * t)})
    row = canonical_feature_row(rec)
    assert row["vibration_x_dominant_frequency_hz"] == pytest.approx(1000.0, abs=fs / (0.1 * fs))
    assert row["n_windows"] == 10                         # 1 s of data / 0.1 s windows
    assert row["vibration_x_rms"] == pytest.approx(1 / np.sqrt(2), rel=1e-3)


def test_short_recording_uses_one_partial_window():
    from bearing_pdm.adapters import BearingRun, Recording
    run = BearingRun("x", "b", "learning", Path("."), 25_600.0, True)
    rec = Recording(run, "r", 0, 0.0, Path("r"),
                    {"vibration_x": np.random.default_rng(0).normal(size=500)})
    row = canonical_feature_row(rec)
    assert row["n_windows"] == 1 and np.isfinite(row["vibration_x_rms"])


def test_inf_samples_are_counted_and_do_not_poison_features():
    from bearing_pdm.adapters import BearingRun, Recording
    x = np.random.default_rng(0).normal(size=2560)
    x[10] = np.inf
    run = BearingRun("x", "b", "learning", Path("."), 25_600.0, True)
    row = canonical_feature_row(Recording(run, "r", 0, 0.0, Path("r"), {"vibration_x": x}))
    assert np.isfinite(row["vibration_x_rms"]) and row["qc_vibration_x_nonfinite"] == 1


def test_signal_quality_flags_constant_clipped_and_empty():
    assert signal_quality(np.ones(100), "c")["qc_c_constant"] == 1.0
    assert signal_quality(np.array([]), "e")["qc_e_constant"] == 1.0
    clipped = np.random.default_rng(0).normal(size=10_000)
    clipped[:500] = clipped.max()                      # sensor sitting on its rail
    assert signal_quality(clipped, "s")["qc_s_clip_fraction"] > 0.04
    assert signal_quality(np.random.default_rng(1).normal(size=10_000), "n")[
        "qc_n_clip_fraction"] < 1e-3


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("header,expected,confidence", [
    ("acc_x", "vibration_x", "high"), ("Accel_X", "vibration_x", "high"),
    ("horizontal_acceleration", "vibration_x", "high"), ("acceleration_y", "vibration_y", "high"),
    ("Horizontal_vibration_signals", "vibration_x", "high"),
    ("my_acc_sensor_x", "vibration_x", "low"), ("pressure", "pressure", "high"),
    ("foo", None, "unmapped"),
])
def test_column_alias_mapping(header, expected, confidence):
    assert map_column(header) == (expected, confidence)


def test_profile_headered_csv_with_low_confidence_warning(tmp_path):
    fs = 1000.0
    t = np.arange(2000) / fs
    pd.DataFrame({"time": t, "my_acc_sensor_x": np.sin(t), "status": ["ok"] * 2000,
                  "dead": 1.0}).to_csv(tmp_path / "a.csv", index=False)
    p = profile_folder(tmp_path)
    assert p["sampling_rate_hz"] == pytest.approx(fs)
    assert p["sampling_rate_source"].startswith("time column")
    warnings = " ".join(p["files"][0]["warnings"])
    assert "low confidence" in warnings and "non-numeric" in warnings and "constant" in warnings
    assert any("no adapter recognises" in w for w in p["warnings"])


def test_profile_empty_and_corrupt_files(tmp_path):
    (tmp_path / "empty.csv").write_text("")
    (tmp_path / "bad.csv").write_text('a,b\n1,2\n3,"4\n')
    assert profile_file(tmp_path / "empty.csv")["warnings"] == ["empty file"]
    bad = profile_file(tmp_path / "bad.csv")
    assert bad["readable"] is False and "corrupt" in bad["warnings"][0]


def test_profile_headerless_file_is_never_guessed(tmp_path):
    np.savetxt(tmp_path / "x.csv", np.random.default_rng(0).normal(size=(100, 4)), delimiter=",")
    p = profile_folder(tmp_path)
    assert all(c["canonical"] is None for c in p["files"][0]["columns"])
    assert p["sampling_rate_hz"] is None


def test_detect_datasets_from_a_single_bearing_folder(tmp_path):
    bearing = _write_xjtu(tmp_path)
    found = detect_datasets(bearing)
    assert [d["dataset_id"] for d in found] == ["xjtu"]
    assert found[0]["root_level"] == "grandparent"
    _write_ims(tmp_path / "ims")
    assert detect_datasets(tmp_path / "ims")[0]["dataset_id"] == "ims"
    assert detect_datasets(tmp_path / "ims" / "2nd_test")[0]["root_level"] == "parent"


def test_ims_test3_is_truncated_at_the_documented_end(tmp_path):
    """Set-3 files after the readme's documented end (2004-04-04 19:01:57) are
    undocumented and must not extend bearing 3's life (docs/decisions.md D22)."""
    d = tmp_path / "4th_test" / "txt"
    d.mkdir(parents=True)
    for name in ("2004.04.04.18.51.57", "2004.04.04.19.01.57", "2004.04.04.19.11.57"):
        np.savetxt(d / name, np.zeros((64, 4)) + 0.1, fmt="%.3f", delimiter="\t")
    adapter = get_adapter("ims")
    run = [r for r in adapter.discover(tmp_path) if r.bearing_id == "test3_bearing3"][0]
    assert [r.recording_id for r in adapter.recordings(run)] == [
        "2004.04.04.18.51.57", "2004.04.04.19.01.57"]


def test_hi_smoothing_window_follows_recording_geometry():
    """~11 fixed 0.1 s windows of smoothing everywhere: 11 one-window FEMTO
    recordings, but 1 for sources whose recording is already a median of many
    windows - otherwise 11 hourly college files would erase a 4-hour cliff."""
    assert get_adapter("femto").hi_smooth_window == 11
    assert {get_adapter(d).hi_smooth_window for d in ("college", "ims", "xjtu")} == {1}
    assert get_adapter("femto").stage_persistence == 5
    assert {get_adapter(d).stage_persistence for d in ("college", "ims", "xjtu")} == {1}
