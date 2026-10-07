"""Case Western Reserve University Bearing Data Center adapter (fault
diagnosis / condition monitoring, NOT run-to-failure). Source and
verification: docs/external-datasets.md.

Each file is a single short recording (one load/fault condition), not a
degradation trajectory - there is no elapsed-time axis and no true RUL
target. CWRU is used here to demonstrate ingestion + feature extraction +
FEMTO-applicability routing on a dataset type the FEMTO model was never fit
on, never to report an RUL metric (ml-data.md: no fabricated RUL ground
truth).

Files are distributed as MATLAB v5 .mat files. Each file carries 2-4
variables named `X<id>_<channel>_time` (DE = drive end accelerometer, FE =
fan end, BA = base) plus `X<id>RPM`. scipy.io.loadmat cannot read every
variable in one call for some of these files (observed: reading a later
variable after an earlier one in the same call raises `OSError: could not
read bytes` - a known scipy/old-MAT-file interaction, not a corrupt
download: `scipy.io.whosmat` and a single-variable read both succeed).
Reading one named variable per call is the reliable path used here.

Dataset-specific parsing only - no feature formulas live here (those are
features.py's job, same adapter boundary as femto.py/college.py/ims.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.io as sio

from bearing_pdm.features import frequency_domain_features, time_domain_features

DATASET_TYPE = "FAULT_DIAGNOSIS"  # never RUN_TO_FAILURE_RUL - see module docstring

# docs/external-datasets.md records the authoritative source and these
# sampling rates per download category.
CWRU_SAMPLE_RATE_HZ = {"12k": 12_000.0, "48k": 48_000.0}

_VAR_RE = re.compile(r"^X(\d+)_(DE|FE|BA)_time$")


@dataclass(frozen=True)
class CwruFile:
    """One CWRU recording: a fault condition snapshot, not a trajectory
    position. `fault_label` is whatever the caller supplies (e.g. from the
    well-known Case Western file-number tables) - this module never infers
    a fault type from the file itself; that would be exactly the kind of
    unverified label ml-data.md prohibits."""

    path: Path
    file_id: str
    fault_label: str
    fault_diameter_in: float | None
    load_hp: float | None
    sample_rate_hz: float


def _variable_names(path: str | Path) -> list[str]:
    return [name for name, _, _ in sio.whosmat(str(path))]


def available_channels(path: str | Path) -> list[str]:
    """Which of DE/FE/BA channels this file actually has, from the mat
    file's own variable list - never assumed from the file id alone."""
    channels = []
    for name in _variable_names(path):
        m = _VAR_RE.match(name)
        if m:
            channels.append(m.group(2))
    return channels


def _find_time_variable(path: str | Path, channel: str) -> str | None:
    """The file id's zero-padding is inconsistent across the real archive
    (observed: file 97 stores its variable as `X097_DE_time`, not
    `X97_DE_time`, while e.g. file 105 stores `X105_DE_time` unpadded) -
    matching on the channel suffix against the file's own variable list
    avoids assuming either convention."""
    suffix = f"_{channel}_time"
    for name in _variable_names(path):
        if name.endswith(suffix):
            return name
    return None


def read_channel(path: str | Path, file_id: str, channel: str = "DE") -> np.ndarray:
    """One channel's time-domain signal as float64, shape (n_samples,).

    `file_id` is accepted for caller bookkeeping/labelling but the actual
    variable name is resolved from the file's own contents (see
    _find_time_variable) - reads only that one named variable (see module
    docstring for why reading multiple variables from one of these files in
    a single loadmat call is unreliable).
    """
    var = _find_time_variable(path, channel)
    if var is None:
        raise ValueError(f"{path}: no {channel!r} channel found (available: {available_channels(path)})")
    data = sio.loadmat(str(path), variable_names=[var])
    return data[var].ravel().astype("float64")


def read_rpm(path: str | Path, file_id: str) -> float | None:
    for name in _variable_names(path):
        if name.endswith("RPM"):
            data = sio.loadmat(str(path), variable_names=[name])
            return float(np.asarray(data[name]).ravel()[0])
    return None


def extract_features(path: str | Path, file_id: str, sample_rate_hz: float, channel: str = "DE") -> dict[str, float]:
    """Time- and frequency-domain features for one CWRU recording's DE
    channel, using the SAME formulas (features.py) the FEMTO/college/IMS
    adapters use - keyed as `vibration_x_*` so the result lines up with
    ApplicabilityModel.feature_columns for an applicability.assess() call.
    CWRU has only this one accelerometer axis per recording (no second
    radial axis the way FEMTO does): there is no `vibration_y_*` here, and a
    caller scoring against a two-axis model must leave those columns NaN
    rather than invent a second channel."""
    signal = read_channel(path, file_id, channel=channel)
    features: dict[str, float] = {}
    features.update(time_domain_features(signal, "vibration_x"))
    features.update(frequency_domain_features(signal, sample_rate_hz, "vibration_x"))
    return features
