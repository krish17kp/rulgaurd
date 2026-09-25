"""Dataset adapters: one canonical recording format for every supported source.

    EXTERNAL DATASET -> adapter -> Recording (canonical) -> same downstream pipeline

The parsing modules (femto.py, college.py, ims.py, xjtu.py) stay dataset-specific
and never learn about each other; this module is the single place that maps each
one onto the canonical names below. Downstream code (pipeline.canonical_feature_row,
the profiler, applicability, routing) only ever sees `BearingRun` / `Recording`,
so it contains no `if dataset == ...` branches.

Canonical channels: `vibration_x`, `vibration_y`, `temperature_bearing`,
`temperature_ambient`. A channel a source does not have is simply absent from
`Recording.signals` - never filled.

Units are carried as recorded: FEMTO, XJTU-SY and IMS report acceleration in g;
the college rig's unit is not stated in its description (docs/external-datasets.md).
Cross-domain features are therefore built as ratios to each bearing's own
healthy reference (domain.py), which is unit-invariant.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from bearing_pdm import college, femto, ims, xjtu

VIBRATION_CHANNELS = ("vibration_x", "vibration_y")

# Roles. `run_to_failure` is a complete external run-to-failure record and may be
# fit on; `survivor` (an IMS bearing that did not fail) has no end-of-life, so it
# can never carry a RUL label or be fit on for RUL.
ROLE_RUN_TO_FAILURE = "run_to_failure"
ROLE_SURVIVOR = "survivor"


@dataclass(frozen=True)
class BearingRun:
    """One bearing's life record plus the operating metadata the applicability
    layer compares against the training domain."""

    dataset_id: str
    bearing_id: str
    role: str
    source: Path
    sampling_rate_hz: float
    run_to_failure: bool
    rpm: float | None = None
    radial_load_n: float | None = None
    operating_condition: str | None = None
    recording_interval_s: float | None = None
    channel_columns: tuple[int, ...] = ()   # IMS: which file columns belong to this bearing

    @property
    def run_id(self) -> str:
        return f"{self.dataset_id}:{self.bearing_id}"


@dataclass(frozen=True)
class Recording:
    run: BearingRun
    recording_id: str
    sequence_index: int
    elapsed_s: float                 # since this bearing's first recording
    source_path: Path
    signals: dict[str, np.ndarray] = field(repr=False)
    timestamp: datetime | None = None


class DatasetAdapter:
    """Interface every dataset implements. `reference_window` = (skip, n): the
    recordings used as each bearing's own healthy reference (domain.py, the
    reference HI). Fixed per dataset from its acquisition cadence, a priori -
    never from a bearing's total life, which is unknown online."""

    dataset_id: str = ""
    display_name: str = ""
    reference_window: tuple[int, int] = (10, 50)
    # Trailing HI smoothing, in recordings. Rule (a priori, from data geometry):
    # smooth over ~11 fixed 0.1 s windows in total. A FEMTO recording is one
    # window, so 11 recordings (health.REFERENCE_HI_SMOOTH_WINDOW, 110 s); IMS,
    # XJTU and college recordings are already medians of 10-780 windows, so 1.
    # A count tuned on FEMTO would otherwise smooth 11 HOURS of college data and
    # erase its 4-hour terminal cliff (docs/decisions.md D26).
    hi_smooth_window: int = 1
    # Stage persistence (consecutive recordings before a stage change commits),
    # same rule: it exists to reject single-snapshot noise, which a many-window
    # recording has already averaged out. FEMTO keeps stages.DEFAULT_PERSISTENCE;
    # 5 hourly college files would outlast its 4-hour terminal cliff.
    stage_persistence: int = 1

    def discover(self, root: str | Path, role: str | None = None) -> list[BearingRun]:
        raise NotImplementedError

    def recordings(self, run: BearingRun) -> Iterator[Recording]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# FEMTO / PRONOSTIA
# ---------------------------------------------------------------------------

# PRONOSTIA operating conditions (Nectoux et al. 2012; command.md table).
FEMTO_CONDITIONS: dict[int, tuple[float, float]] = {
    1: (1800.0, 4000.0), 2: (1650.0, 4200.0), 3: (1500.0, 5000.0),
}


class FemtoAdapter(DatasetAdapter):
    dataset_id = "femto"
    display_name = "FEMTO-ST / PRONOSTIA (IEEE PHM 2012)"
    reference_window = (10, 50)   # == health.REFERENCE_HI_SKIP / REFERENCE_HI_N
    hi_smooth_window = 11         # == health.REFERENCE_HI_SMOOTH_WINDOW
    stage_persistence = 5         # == stages.DEFAULT_PERSISTENCE

    def discover(self, root, role=femto.ROLE_LEARNING):
        role = role or femto.ROLE_LEARNING
        runs = []
        for b in femto.discover_femto_bearings(root, role=role):
            # A BearingC_N folder name alone is not FEMTO (XJTU-SY uses the same
            # names): it must hold acc_NNNNN.csv acquisitions.
            if b.condition_id not in FEMTO_CONDITIONS or not femto.list_acquisition_indices(b.path):
                continue
            rpm, load = FEMTO_CONDITIONS[b.condition_id]
            runs.append(BearingRun(
                dataset_id=self.dataset_id, bearing_id=b.bearing_label, role=role, source=b.path,
                sampling_rate_hz=25_600.0,
                # Learning and full-test bearings are complete runs; the censored
                # test prefix is not (its end is the hidden label).
                run_to_failure=role != femto.ROLE_TEST_CENSORED,
                rpm=rpm, radial_load_n=load, operating_condition=f"condition {b.condition_id}",
                recording_interval_s=femto.ACQUISITION_INTERVAL_S,
            ))
        return runs

    def recordings(self, run):
        indices = femto.list_acquisition_indices(run.source)
        temp_index = femto.build_temperature_time_index(run.source)
        for seq, idx in enumerate(indices):
            acc = femto.read_acceleration(run.source, idx)
            signals = {
                "vibration_x": acc["accel_horizontal"].to_numpy(),
                "vibration_y": acc["accel_vertical"].to_numpy(),
            }
            first = acc.iloc[0]
            t_idx = femto.find_nearest_temperature_index(
                run.source, idx, temp_time_index=temp_index,
                acc_time_s=first["hour"] * 3600.0 + first["minute"] * 60.0 + first["second"],
            )
            if t_idx is not None:
                signals["temperature_bearing"] = (
                    femto.read_temperature(run.source, t_idx)["temperature_c"].to_numpy()
                )
            yield Recording(
                run=run, recording_id=f"acc_{idx:05d}", sequence_index=seq,
                elapsed_s=(idx - indices[0]) * femto.ACQUISITION_INTERVAL_S,
                source_path=run.source / f"acc_{idx:05d}.csv", signals=signals,
            )


# ---------------------------------------------------------------------------
# College rig (one NSK 6205 bearing, one run)
# ---------------------------------------------------------------------------


class CollegeAdapter(DatasetAdapter):
    dataset_id = "college"
    display_name = "College rig run-to-failure (NSK 6205, 1 bearing)"
    # 129 hourly files: skip the first hour, use hours 1-5 as the healthy
    # reference (a 50-recording window would be ~40% of this run).
    reference_window = (1, 5)

    def discover(self, root, role=None):
        # Fail early on an empty/unknown folder, same as the parser.
        college.discover_college_files(root)
        return [BearingRun(
            dataset_id=self.dataset_id, bearing_id="nsk6205", role="college_run",
            source=Path(root), sampling_rate_hz=25_600.0, run_to_failure=True,
            rpm=1775.0, radial_load_n=5880.0,
            operating_condition="1770-1780 rpm, 5.88 kN vertical + 2.94 kN axial",
            recording_interval_s=3600.0,
        )]

    def recordings(self, run):
        files = college.discover_college_files(run.source)
        t0 = files[0].timestamp
        for f in files:
            # ponytail: one whole file (2M rows, ~64 MB) is materialised per
            # recording, read in bounded chunks; the 18 GB run never is.
            chunks = list(college.read_college_chunks(f.path))
            data = pd.concat(chunks, ignore_index=True)
            yield Recording(
                run=run, recording_id=f.path.name, sequence_index=f.sequence_index,
                elapsed_s=(f.timestamp - t0).total_seconds(), source_path=f.path,
                timestamp=f.timestamp,
                signals={
                    "vibration_x": data["vibration_x"].to_numpy(),
                    "vibration_y": data["vibration_y"].to_numpy(),
                    "temperature_bearing": data["bearing_temp_c"].to_numpy(),
                    "temperature_ambient": data["ambient_temp_c"].to_numpy(),
                },
            )


# ---------------------------------------------------------------------------
# IMS (NASA)
# ---------------------------------------------------------------------------


class ImsAdapter(DatasetAdapter):
    dataset_id = "ims"
    display_name = "IMS / NASA bearing run-to-failure (Univ. of Cincinnati)"
    reference_window = (10, 50)   # 10-min cadence: ~1.5 h skipped, next ~8 h

    def discover(self, root, role=None):
        runs = []
        for test_id, (_subs, bearings) in ims.IMS_TESTS.items():
            test_dir = ims.resolve_test_dir(root, test_id)
            if test_dir is None:
                continue
            for number, cols in bearings.items():
                failed = (test_id, number) in ims.IMS_FAILED_BEARINGS
                run_role = ROLE_RUN_TO_FAILURE if failed else ROLE_SURVIVOR
                if role is not None and role != run_role:
                    continue
                runs.append(BearingRun(
                    dataset_id=self.dataset_id, bearing_id=f"test{test_id}_bearing{number}",
                    role=run_role, source=test_dir, sampling_rate_hz=ims.IMS_SAMPLE_RATE_HZ,
                    run_to_failure=failed, rpm=ims.IMS_RPM, radial_load_n=ims.IMS_RADIAL_LOAD_N,
                    operating_condition=f"test {test_id}", recording_interval_s=600.0,
                    channel_columns=cols,
                ))
        if not runs:
            raise FileNotFoundError(f"No IMS test folders (1st_test/2nd_test/...) under {root}")
        return runs

    def recordings(self, run):
        test_id = run.bearing_id[len("test")]
        n_columns = 8 if test_id == "1" else 4
        files = ims.list_ims_files(run.source, end=ims.IMS_DOCUMENTED_END.get(test_id))
        t0 = files[0][1]
        for seq, (path, ts) in enumerate(files):
            data = ims.read_ims_file(path, n_columns)
            signals = {ch: data[:, col] for ch, col in zip(VIBRATION_CHANNELS, run.channel_columns)}
            yield Recording(
                run=run, recording_id=path.name, sequence_index=seq,
                elapsed_s=(ts - t0).total_seconds(), source_path=path, timestamp=ts,
                signals=signals,
            )


# ---------------------------------------------------------------------------
# XJTU-SY
# ---------------------------------------------------------------------------


class XjtuAdapter(DatasetAdapter):
    dataset_id = "xjtu"
    display_name = "XJTU-SY bearing run-to-failure (Xi'an Jiaotong Univ.)"
    # 1-min cadence and runs as short as 42 recordings: skip 2, use the next 10.
    reference_window = (2, 10)

    def discover(self, root, role=None):
        runs = []
        for condition, bdir in xjtu.discover_xjtu_bearings(root):
            rpm, load, cid = xjtu.XJTU_CONDITIONS[condition]
            runs.append(BearingRun(
                dataset_id=self.dataset_id, bearing_id=bdir.name, role=ROLE_RUN_TO_FAILURE,
                source=bdir, sampling_rate_hz=xjtu.XJTU_SAMPLE_RATE_HZ, run_to_failure=True,
                rpm=rpm, radial_load_n=load, operating_condition=f"condition {cid} ({condition})",
                recording_interval_s=xjtu.XJTU_RECORDING_INTERVAL_S,
            ))
        if not runs:
            raise FileNotFoundError(f"No XJTU-SY condition folders (35Hz12kN/...) under {root}")
        return runs

    def recordings(self, run):
        for seq, path in enumerate(xjtu.list_xjtu_files(run.source)):
            df = xjtu.read_xjtu_file(path)
            yield Recording(
                run=run, recording_id=path.name, sequence_index=seq,
                elapsed_s=seq * xjtu.XJTU_RECORDING_INTERVAL_S, source_path=path,
                signals={
                    "vibration_x": df["Horizontal_vibration_signals"].to_numpy(),
                    "vibration_y": df["Vertical_vibration_signals"].to_numpy(),
                },
            )


ADAPTERS: dict[str, DatasetAdapter] = {
    a.dataset_id: a for a in (FemtoAdapter(), CollegeAdapter(), ImsAdapter(), XjtuAdapter())
}


def get_adapter(dataset_id: str) -> DatasetAdapter:
    try:
        return ADAPTERS[dataset_id]
    except KeyError:
        raise ValueError(
            f"Unknown dataset '{dataset_id}'. Supported: {sorted(ADAPTERS)}. "
            "Profile an unknown folder with profiler.profile_folder() instead."
        ) from None
