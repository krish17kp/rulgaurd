"""Self-normalised ("SN") features: the cross-domain feature representation.

Why this exists. Absolute vibration features are not comparable across rigs:
sensor model and mounting, units (the college rig's are unstated), load (4 kN on
FEMTO vs 26.7 kN on IMS), speed and sampling rate all move them. A model fit on
FEMTO's absolute RMS therefore sees a new machine as out-of-distribution before
it has degraded at all. What IS comparable is *change relative to the same
bearing's own healthy state* - the standard normalisation in cross-domain
bearing prognostics, and the same idea the reference HI already uses
(health.py, docs/decisions.md D19).

Definition, per bearing, per recording, for each available vibration channel:

    amplitude / ratio features   sn = log(x) - median(log x over reference window)
    fraction / signed features   sn = x - median(x over reference window)

then averaged over the channels the source actually has (IMS tests 2-3 have
one accelerometer per bearing, FEMTO/XJTU/college two), so a missing channel
reduces information but never produces a fabricated value.

The reference window is `adapters.DatasetAdapter.reference_window` =
(skip, n) recordings, fixed per dataset from its acquisition cadence. It lies in
each bearing's own past, so the representation is causal and computable online
for a bearing never seen before. Rows inside the window are near zero by
construction and are excluded from evaluation (`after_reference_window`).

A log ratio is unit-invariant (g vs m/s^2 cancels), so the unverified college
unit cannot bias these features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bearing_pdm.adapters import VIBRATION_CHANNELS, get_adapter

# (feature suffix, transform). "log": log-ratio to the reference; "diff": difference.
# Kurtosis is Fisher/excess (can be negative), so +3 makes it Pearson kurtosis
# (>= 1) before the log.
SN_SPEC: dict[str, str] = {
    "rms": "log",
    "peak_to_peak": "log",
    "kurtosis": "log_pearson",
    "crest_factor": "log",
    "impulse_factor": "log",
    "shape_factor": "log",
    "clearance_factor": "log",
    "skewness": "diff",
    "spectral_centroid_hz": "log",
    "frequency_rms_hz": "log",
    "spectral_entropy": "diff",
    "band_energy_frac_low": "diff",
    "band_energy_frac_mid": "diff",
    "band_energy_frac_high": "diff",
}
SN_FEATURES: list[str] = [f"sn_{name}" for name in SN_SPEC]

_EPS = 1e-12


def reference_window(dataset_id: str) -> tuple[int, int]:
    return get_adapter(dataset_id).reference_window


def hi_smooth_window(dataset_id: str) -> int:
    return get_adapter(dataset_id).hi_smooth_window


def stage_persistence(dataset_id: str) -> int:
    return get_adapter(dataset_id).stage_persistence


def _transform(values: pd.Series, kind: str) -> pd.Series:
    v = values.astype(float)
    if kind == "log":
        return np.log(v.clip(lower=_EPS))
    if kind == "log_pearson":
        return np.log((v + 3.0).clip(lower=_EPS))
    return v


def add_self_normalized_features(df: pd.DataFrame) -> pd.DataFrame:
    """Copy of `df` with the `sn_*` columns added. Needs dataset_id,
    bearing_run_id, sequence_index and the canonical vibration feature columns.
    Nothing is fit here: every reference is the bearing's own past."""
    out = df.copy()
    for name in SN_SPEC:
        out[f"sn_{name}"] = np.nan
    for _run, group in out.groupby("bearing_run_id", sort=False):
        skip, n_ref = reference_window(group["dataset_id"].iloc[0])
        ordered = group.sort_values("sequence_index").index
        window = ordered[skip:skip + n_ref]
        if len(window) == 0:              # shorter than the skip: best available
            window = ordered[:n_ref]
        for name, kind in SN_SPEC.items():
            per_channel = []
            for ch in VIBRATION_CHANNELS:
                col = f"{ch}_{name}"
                if col not in out.columns or out.loc[ordered, col].isna().all():
                    continue
                t = _transform(out.loc[ordered, col], kind)
                per_channel.append(t - t.loc[window].median())
            if per_channel:
                out.loc[ordered, f"sn_{name}"] = pd.concat(per_channel, axis=1).mean(axis=1)
    return out


def after_reference_window(df: pd.DataFrame) -> pd.Series:
    """True for recordings strictly after their bearing's reference window -
    the rows on which SN features carry information and on which every
    cross-domain model is evaluated."""
    limit = df["dataset_id"].map(lambda d: sum(reference_window(d)))
    return df["sequence_index"] >= limit
